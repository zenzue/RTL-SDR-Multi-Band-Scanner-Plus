#!/usr/bin/env python3
"""
Receive-only RTL-SDR scanner for authorized RF assessment.

Features:
- Multi-band scanning with rtl_power
- Dynamic noise-floor thresholding
- Peak clustering so one transmission is not shown as many adjacent bins
- Safe listener process handling: rtl_fm -> aplay
- CSV logging for red-team/report evidence
- Blocks listening to protected/emergency guard frequencies by default

Requirements:
    sudo apt install rtl-sdr alsa-utils python3
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# ================== DEFAULT CONFIG ==================
DEFAULT_GAIN = 40
DEFAULT_PPM = 0
DEFAULT_INTEGRATION_SEC = 2
DEFAULT_THRESHOLD_OFFSET_DB = 12.0
DEFAULT_MIN_ABSOLUTE_DB = -60.0
DEFAULT_MAX_RESULTS = 15
DEFAULT_LOG_DIR = "./sdr_logs"

# Keep emergency/protected channels out of interactive listening.
PROTECTED_FREQS_MHZ = {
    121.500: "Aviation emergency guard frequency",
    243.000: "Military aviation emergency guard frequency",
}
PROTECTED_TOLERANCE_KHZ = 12.5


@dataclass(frozen=True)
class BandConfig:
    key: str
    name: str
    low_mhz: float
    high_mhz: float
    step_khz: float
    mode: str
    audio_rate: int
    note: str = ""


@dataclass(frozen=True)
class SignalPeak:
    freq_mhz: float
    db: float
    threshold_db: float
    noise_floor_db: float
    protected_reason: str | None = None


BANDS: dict[str, BandConfig] = {
    "1": BandConfig(
        key="1",
        name="Airband AM, authorized receive-only scan",
        low_mhz=118.0,
        high_mhz=137.0,
        step_khz=25.0,
        mode="am",
        audio_rate=48000,
        note="Use only inside your written test scope. Emergency guard is blocked.",
    ),
    "2": BandConfig(
        key="2",
        name="Authorized UHF land-mobile range",
        low_mhz=450.0,
        high_mhz=470.0,
        step_khz=12.5,
        mode="fm",
        audio_rate=24000,
        note="Confirm the exact local allocation and client-approved frequencies first.",
    ),
    "3": BandConfig(
        key="3",
        name="Authorized portable-radio test range",
        low_mhz=462.0,
        high_mhz=468.0,
        step_khz=12.5,
        mode="fm",
        audio_rate=24000,
        note="FRS/GMRS-style ranges are jurisdiction-specific. Use only if approved.",
    ),
}


current_audio_procs: list[subprocess.Popen] = []


def which_or_none(tool: str) -> str | None:
    return shutil.which(tool)


def require_scan_tools() -> None:
    missing = [tool for tool in ["rtl_power", "rtl_fm"] if not which_or_none(tool)]

    if missing:
        print(f"❌ Missing required tool(s): {', '.join(missing)}")
        print("Install RTL-SDR tools first:")
        print("  sudo apt install rtl-sdr")
        sys.exit(1)

    if not which_or_none("aplay"):
        print("⚠️  aplay was not found. Scanning works, but listening will not work.")
        print("Install it with:")
        print("  sudo apt install alsa-utils")


def kill_process_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as exc:
        print(f"⚠️  Failed to stop process {proc.pid}: {exc}")


def stop_audio() -> None:
    global current_audio_procs

    for proc in current_audio_procs:
        kill_process_group(proc)

    current_audio_procs = []


def protected_reason(freq_mhz: float) -> str | None:
    tolerance_mhz = PROTECTED_TOLERANCE_KHZ / 1000.0

    for protected_freq, reason in PROTECTED_FREQS_MHZ.items():
        if abs(freq_mhz - protected_freq) <= tolerance_mhz:
            return reason

    return None


def build_rtl_power_cmd(
    cfg: BandConfig,
    args: argparse.Namespace,
    output_csv: Path,
) -> list[str]:
    cmd = [
        "rtl_power",
        "-f",
        f"{cfg.low_mhz}M:{cfg.high_mhz}M:{cfg.step_khz}k",
        "-g",
        str(args.gain),
        "-i",
        str(args.integration),
        "-1",
        "-p",
        str(args.ppm),
    ]

    if args.device is not None:
        cmd.extend(["-d", str(args.device)])

    cmd.append(str(output_csv))
    return cmd


def run_rtl_power(
    cfg: BandConfig,
    args: argparse.Namespace,
    output_csv: Path,
) -> bool:
    # Important: rtl_fm and rtl_power cannot use the same dongle together.
    stop_audio()

    cmd = build_rtl_power_cmd(cfg, args, output_csv)

    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        return True

    except subprocess.CalledProcessError as exc:
        print("❌ rtl_power failed")

        err = (exc.stderr or "").strip()
        if err:
            print(err)
        else:
            print("No stderr returned.")
            print("Check RTL-SDR connection, USB permission, and device busy state.")

        return False


def parse_power_csv(path: Path, cfg: BandConfig) -> list[tuple[float, float]]:
    """
    Return:
        [(freq_mhz, db), ...]
    """

    bins: list[tuple[float, float]] = []

    try:
        with path.open("r", newline="") as file:
            reader = csv.reader(file)

            for row in reader:
                if len(row) < 7:
                    continue

                try:
                    low_hz = float(row[2])
                    step_hz = float(row[4])
                    db_values = [float(x) for x in row[6:] if x.strip()]
                except ValueError:
                    continue

                for idx, db in enumerate(db_values):
                    freq_mhz = (low_hz + idx * step_hz) / 1_000_000.0

                    if cfg.low_mhz <= freq_mhz <= cfg.high_mhz:
                        bins.append((freq_mhz, db))

    except FileNotFoundError:
        print(f"❌ Scan output not found: {path}")

    return bins


def calculate_threshold(
    db_values: Iterable[float],
    args: argparse.Namespace,
) -> tuple[float, float]:
    values = list(db_values)

    if not values:
        return args.min_db, args.min_db

    noise_floor = statistics.median(values)
    dynamic_threshold = noise_floor + args.threshold_offset
    threshold = max(dynamic_threshold, args.min_db)

    return noise_floor, threshold


def cluster_active_bins(
    active_bins: list[tuple[float, float]],
    cfg: BandConfig,
    threshold_db: float,
    noise_floor_db: float,
) -> list[SignalPeak]:
    """
    Merge nearby active bins and keep the strongest bin per cluster.
    """

    if not active_bins:
        return []

    active_bins.sort(key=lambda item: item[0])

    merge_width_mhz = max(cfg.step_khz * 2.0, cfg.step_khz) / 1000.0

    clusters: list[list[tuple[float, float]]] = []
    current_cluster: list[tuple[float, float]] = [active_bins[0]]

    for freq_mhz, db in active_bins[1:]:
        previous_freq = current_cluster[-1][0]

        if freq_mhz - previous_freq <= merge_width_mhz:
            current_cluster.append((freq_mhz, db))
        else:
            clusters.append(current_cluster)
            current_cluster = [(freq_mhz, db)]

    clusters.append(current_cluster)

    peaks: list[SignalPeak] = []

    for cluster in clusters:
        peak_freq, peak_db = max(cluster, key=lambda item: item[1])

        peaks.append(
            SignalPeak(
                freq_mhz=round(peak_freq, 4),
                db=round(peak_db, 1),
                threshold_db=round(threshold_db, 1),
                noise_floor_db=round(noise_floor_db, 1),
                protected_reason=protected_reason(peak_freq),
            )
        )

    peaks.sort(key=lambda peak: peak.db, reverse=True)

    return peaks


def scan_band(cfg: BandConfig, args: argparse.Namespace) -> list[SignalPeak]:
    print(f"\n📡 Scanning: {cfg.name}")
    print(
        f"   Range: {cfg.low_mhz:.3f}-{cfg.high_mhz:.3f} MHz | "
        f"Step: {cfg.step_khz:g} kHz | "
        f"Mode: {cfg.mode.upper()}"
    )

    with tempfile.NamedTemporaryFile(
        prefix="rtl_power_",
        suffix=".csv",
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        if not run_rtl_power(cfg, args, tmp_path):
            return []

        bins = parse_power_csv(tmp_path, cfg)

        if not bins:
            print("⚠️  No bins parsed from rtl_power output.")
            return []

        noise_floor, threshold = calculate_threshold(
            (db for _, db in bins),
            args,
        )

        active_bins = [
            (freq, db)
            for freq, db in bins
            if db >= threshold
        ]

        peaks = cluster_active_bins(
            active_bins,
            cfg,
            threshold,
            noise_floor,
        )

        save_scan_log(cfg, peaks, args)

        print(
            f"   Noise floor: {noise_floor:.1f} dB | "
            f"Active threshold: {threshold:.1f} dB"
        )

        return peaks

    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def save_scan_log(
    cfg: BandConfig,
    peaks: list[SignalPeak],
    args: argparse.Namespace,
) -> None:
    if not args.log:
        return

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "active_signals.csv"
    is_new = not log_file.exists()
    now = dt.datetime.now().isoformat(timespec="seconds")

    with log_file.open("a", newline="") as file:
        writer = csv.writer(file)

        if is_new:
            writer.writerow(
                [
                    "timestamp",
                    "band_key",
                    "band_name",
                    "freq_mhz",
                    "db",
                    "noise_floor_db",
                    "threshold_db",
                    "protected_reason",
                ]
            )

        for peak in peaks:
            writer.writerow(
                [
                    now,
                    cfg.key,
                    cfg.name,
                    f"{peak.freq_mhz:.4f}",
                    f"{peak.db:.1f}",
                    f"{peak.noise_floor_db:.1f}",
                    f"{peak.threshold_db:.1f}",
                    peak.protected_reason or "",
                ]
            )


def print_peaks(peaks: list[SignalPeak], args: argparse.Namespace) -> None:
    print("\n📊 Active channels, strongest first:")

    if not peaks:
        print(
            "   None above threshold. Try increasing gain, better antenna, "
            "longer integration, or lower --threshold-offset."
        )
        return

    for idx, peak in enumerate(peaks[: args.max_results], start=1):
        over = max(0, peak.db - peak.threshold_db)
        bar = "█" * min(40, int(over / 1.5))
        lock = " 🔒" if peak.protected_reason else ""

        print(
            f"  {idx:2d}. {peak.freq_mhz:9.4f} MHz  "
            f"{peak.db:6.1f} dB  "
            f"+{over:4.1f} over threshold  {bar}{lock}"
        )

        if peak.protected_reason:
            print(f"      Protected: {peak.protected_reason}")


def listen_to_frequency(
    freq_mhz: float,
    cfg: BandConfig,
    args: argparse.Namespace,
) -> None:
    reason = protected_reason(freq_mhz)

    if reason:
        print(f"🚫 Listening blocked for {freq_mhz:.4f} MHz: {reason}")
        print("   Keep emergency/protected frequencies out of interactive listening.")
        return

    if not which_or_none("aplay"):
        print("❌ aplay not installed, cannot listen.")
        print("Install it with:")
        print("  sudo apt install alsa-utils")
        return

    stop_audio()

    rtl_cmd = [
        "rtl_fm",
        "-f",
        str(int(freq_mhz * 1_000_000)),
        "-M",
        cfg.mode,
        "-s",
        str(cfg.audio_rate),
        "-g",
        str(args.gain),
        "-p",
        str(args.ppm),
    ]

    if args.device is not None:
        rtl_cmd.extend(["-d", str(args.device)])

    rtl_cmd.append("-")

    aplay_cmd = [
        "aplay",
        "-r",
        str(cfg.audio_rate),
        "-f",
        "S16_LE",
        "-t",
        "raw",
        "-c",
        "1",
    ]

    print(
        f"\n🎙️  Listening: {freq_mhz:.4f} MHz | "
        f"{cfg.mode.upper()} | "
        f"{cfg.audio_rate} Hz"
    )
    print("   Press Enter or Ctrl+C to stop listening and return to scanner.\n")

    global current_audio_procs

    try:
        rtl_proc = subprocess.Popen(
            rtl_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        if rtl_proc.stdout is None:
            print("❌ Failed to open rtl_fm audio pipe.")
            stop_audio()
            return

        aplay_proc = subprocess.Popen(
            aplay_cmd,
            stdin=rtl_proc.stdout,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        rtl_proc.stdout.close()

        current_audio_procs = [rtl_proc, aplay_proc]

        try:
            input()
        except KeyboardInterrupt:
            print()

    finally:
        stop_audio()
        print("🔁 Back to scanner")


def print_menu() -> None:
    print("\n🚁 RTL-SDR Multi-Band Scanner Plus")
    print("Receive-only. Use only for authorized RF assessment. No transmit. No decrypt.\n")

    for key, cfg in BANDS.items():
        print(f"{key} = {cfg.name}")
        print(
            f"    {cfg.low_mhz:.3f}-{cfg.high_mhz:.3f} MHz | "
            f"{cfg.step_khz:g} kHz | "
            f"{cfg.mode.upper()}"
        )

        if cfg.note:
            print(f"    Note: {cfg.note}")

    print("q = quit")


def band_loop(cfg: BandConfig, args: argparse.Namespace) -> bool:
    while True:
        peaks = scan_band(cfg, args)
        print_peaks(peaks, args)

        print("\n[ number ] = Listen")
        print("[ Enter ]  = Rescan")
        print("[ b ]      = Change band")
        print("[ q ]      = Quit")

        action = input("\n> ").strip().lower()

        if action == "q":
            return False

        if action == "b":
            return True

        if action == "":
            continue

        if action.isdigit():
            idx = int(action) - 1

            if 0 <= idx < min(len(peaks), args.max_results):
                listen_to_frequency(peaks[idx].freq_mhz, cfg, args)
            else:
                print("Invalid number")

            continue

        print("Choose Enter, a number, b, or q.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Receive-only RTL-SDR scanner for authorized RF assessment."
    )

    parser.add_argument(
        "--gain",
        type=float,
        default=DEFAULT_GAIN,
        help="RTL-SDR gain. Default: 40",
    )

    parser.add_argument(
        "--ppm",
        type=int,
        default=DEFAULT_PPM,
        help="PPM correction. Default: 0",
    )

    parser.add_argument(
        "--integration",
        type=float,
        default=DEFAULT_INTEGRATION_SEC,
        help="rtl_power integration seconds. Default: 2",
    )

    parser.add_argument(
        "--threshold-offset",
        type=float,
        default=DEFAULT_THRESHOLD_OFFSET_DB,
        help="dB above median noise floor. Default: 12",
    )

    parser.add_argument(
        "--min-db",
        type=float,
        default=DEFAULT_MIN_ABSOLUTE_DB,
        help="Minimum absolute active threshold. Default: -60",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help="Maximum listed peaks. Default: 15",
    )

    parser.add_argument(
        "--log-dir",
        default=DEFAULT_LOG_DIR,
        help="CSV log directory. Default: ./sdr_logs",
    )

    parser.add_argument(
        "--no-log",
        dest="log",
        action="store_false",
        help="Disable CSV logging",
    )

    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="RTL-SDR device index, example: --device 0",
    )

    parser.set_defaults(log=True)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_scan_tools()

    while True:
        print_menu()

        choice = input("\nChoose band: ").strip().lower()

        if choice == "q":
            break

        cfg = BANDS.get(choice)

        if not cfg:
            print("Invalid choice.")
            continue

        should_continue = band_loop(cfg, args)

        if not should_continue:
            break

    stop_audio()
    print("👋 Done. Logs saved in:", Path(args.log_dir).resolve())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        stop_audio()
        print("\n🛑 Stopped")
        sys.exit(0)