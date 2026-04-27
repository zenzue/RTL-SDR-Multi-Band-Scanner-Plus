#!/usr/bin/env python3
"""
RTL-SDR CLI Scanner Plus
Author: Aung Myat Thu

Receive-only SDR scanner.
Scan frequencies, choose active channel by number, and play audio from CLI.

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


# ================== DEFAULT CONFIG ==================

DEFAULT_GAIN = 40
DEFAULT_PPM = 0
DEFAULT_INTEGRATION_SEC = 2
DEFAULT_THRESHOLD_OFFSET_DB = 12.0
DEFAULT_MIN_DB = -65.0
DEFAULT_MAX_RESULTS = 20
DEFAULT_LOG_DIR = "./sdr_logs"

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
    rtl_rate: int
    audio_rate: int
    note: str = ""


@dataclass(frozen=True)
class SignalPeak:
    freq_mhz: float
    db: float
    noise_floor_db: float
    threshold_db: float
    protected_reason: str | None = None


BANDS: dict[str, BandConfig] = {
    "1": BandConfig(
        key="1",
        name="FM Broadcast Radio",
        low_mhz=87.5,
        high_mhz=108.0,
        step_khz=100.0,
        mode="wbfm",
        rtl_rate=200000,
        audio_rate=48000,
        note="Good beginner test band.",
    ),
    "2": BandConfig(
        key="2",
        name="Airband AM",
        low_mhz=118.0,
        high_mhz=137.0,
        step_khz=25.0,
        mode="am",
        rtl_rate=48000,
        audio_rate=48000,
        note="Use only where legal and authorized. Emergency guard frequency is blocked.",
    ),
    "3": BandConfig(
        key="3",
        name="Authorized UHF Land Mobile Range",
        low_mhz=450.0,
        high_mhz=470.0,
        step_khz=12.5,
        mode="fm",
        rtl_rate=24000,
        audio_rate=24000,
        note="Confirm local frequency allocation and written test scope.",
    ),
    "4": BandConfig(
        key="4",
        name="Authorized Portable Radio Test Range",
        low_mhz=462.0,
        high_mhz=468.0,
        step_khz=12.5,
        mode="fm",
        rtl_rate=24000,
        audio_rate=24000,
        note="Jurisdiction-specific. Use only inside approved scope.",
    ),
}


current_audio_procs: list[subprocess.Popen] = []


# ================== BASIC HELPERS ==================

def require_tools() -> None:
    missing = []

    for tool in ["rtl_power", "rtl_fm"]:
        if not shutil.which(tool):
            missing.append(tool)

    if missing:
        print(f"❌ Missing required tools: {', '.join(missing)}")
        print("Install with:")
        print("  sudo apt install rtl-sdr")
        sys.exit(1)

    if not shutil.which("aplay"):
        print("❌ Missing required tool: aplay")
        print("Install with:")
        print("  sudo apt install alsa-utils")
        sys.exit(1)


def protected_reason(freq_mhz: float) -> str | None:
    tolerance_mhz = PROTECTED_TOLERANCE_KHZ / 1000.0

    for protected_freq, reason in PROTECTED_FREQS_MHZ.items():
        if abs(freq_mhz - protected_freq) <= tolerance_mhz:
            return reason

    return None


def stop_audio() -> None:
    global current_audio_procs

    for proc in current_audio_procs:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as exc:
                print(f"⚠️ Failed to stop process {proc.pid}: {exc}")

    current_audio_procs = []


def signal_handler(sig, frame) -> None:
    stop_audio()
    print("\n🛑 Stopped")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


# ================== SCANNING ==================

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

        if exc.stderr:
            print(exc.stderr.strip())
        else:
            print("No error message returned.")

        print("\nPossible fixes:")
        print("  - Check RTL-SDR USB connection")
        print("  - Run: rtl_test")
        print("  - Kill old process: pkill rtl_fm rtl_power rtl_tcp")
        print("  - Check DVB driver blacklist")
        return False


def parse_power_csv(path: Path, cfg: BandConfig) -> list[tuple[float, float]]:
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
        print(f"❌ Missing scan output file: {path}")

    return bins


def calculate_threshold(
    db_values: list[float],
    args: argparse.Namespace,
) -> tuple[float, float]:
    if not db_values:
        return args.min_db, args.min_db

    noise_floor = statistics.median(db_values)
    dynamic_threshold = noise_floor + args.threshold_offset
    threshold = max(dynamic_threshold, args.min_db)

    return noise_floor, threshold


def cluster_active_bins(
    active_bins: list[tuple[float, float]],
    cfg: BandConfig,
    noise_floor: float,
    threshold: float,
) -> list[SignalPeak]:
    if not active_bins:
        return []

    active_bins.sort(key=lambda item: item[0])

    merge_width_mhz = max(cfg.step_khz * 2, cfg.step_khz) / 1000.0

    clusters: list[list[tuple[float, float]]] = []
    cluster: list[tuple[float, float]] = [active_bins[0]]

    for freq_mhz, db in active_bins[1:]:
        previous_freq = cluster[-1][0]

        if freq_mhz - previous_freq <= merge_width_mhz:
            cluster.append((freq_mhz, db))
        else:
            clusters.append(cluster)
            cluster = [(freq_mhz, db)]

    clusters.append(cluster)

    peaks: list[SignalPeak] = []

    for item in clusters:
        peak_freq, peak_db = max(item, key=lambda x: x[1])

        peaks.append(
            SignalPeak(
                freq_mhz=round(peak_freq, 4),
                db=round(peak_db, 1),
                noise_floor_db=round(noise_floor, 1),
                threshold_db=round(threshold, 1),
                protected_reason=protected_reason(peak_freq),
            )
        )

    peaks.sort(key=lambda peak: peak.db, reverse=True)
    return peaks


def scan_band(cfg: BandConfig, args: argparse.Namespace) -> list[SignalPeak]:
    print(f"\n📡 Scanning {cfg.name}")
    print(
        f"   Range: {cfg.low_mhz:.3f}-{cfg.high_mhz:.3f} MHz | "
        f"Step: {cfg.step_khz:g} kHz | "
        f"Mode: {cfg.mode.upper()}"
    )

    with tempfile.NamedTemporaryFile(
        prefix="rtl_power_",
        suffix=".csv",
        delete=False,
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        ok = run_rtl_power(cfg, args, tmp_path)

        if not ok:
            return []

        bins = parse_power_csv(tmp_path, cfg)

        if not bins:
            print("⚠️ No frequency bins found.")
            return []

        db_values = [db for _, db in bins]
        noise_floor, threshold = calculate_threshold(db_values, args)

        active_bins = [
            (freq, db)
            for freq, db in bins
            if db >= threshold
        ]

        peaks = cluster_active_bins(
            active_bins=active_bins,
            cfg=cfg,
            noise_floor=noise_floor,
            threshold=threshold,
        )

        save_log(cfg, peaks, args)

        print(
            f"   Noise floor: {noise_floor:.1f} dB | "
            f"Threshold: {threshold:.1f} dB"
        )

        return peaks

    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ================== LOGGING ==================

def save_log(
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
                    "band",
                    "frequency_mhz",
                    "mode",
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
                    cfg.name,
                    f"{peak.freq_mhz:.4f}",
                    cfg.mode,
                    f"{peak.db:.1f}",
                    f"{peak.noise_floor_db:.1f}",
                    f"{peak.threshold_db:.1f}",
                    peak.protected_reason or "",
                ]
            )


# ================== AUDIO PLAYBACK ==================

def build_rtl_fm_cmd(
    freq_mhz: float,
    cfg: BandConfig,
    args: argparse.Namespace,
) -> list[str]:
    cmd = [
        "rtl_fm",
        "-f",
        str(int(freq_mhz * 1_000_000)),
        "-M",
        cfg.mode,
        "-s",
        str(cfg.rtl_rate),
        "-g",
        str(args.gain),
        "-p",
        str(args.ppm),
    ]

    # WBFM needs audio resampling for clean playback.
    if cfg.mode == "wbfm":
        cmd.extend(["-r", str(cfg.audio_rate)])

    if args.device is not None:
        cmd.extend(["-d", str(args.device)])

    cmd.append("-")
    return cmd


def build_aplay_cmd(cfg: BandConfig, args: argparse.Namespace) -> list[str]:
    cmd = [
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

    if args.audio_device:
        cmd.extend(["-D", args.audio_device])

    return cmd


def play_frequency(
    freq_mhz: float,
    cfg: BandConfig,
    args: argparse.Namespace,
) -> None:
    reason = protected_reason(freq_mhz)

    if reason:
        print(f"\n🚫 Blocked: {freq_mhz:.4f} MHz")
        print(f"Reason: {reason}")
        return

    stop_audio()

    rtl_cmd = build_rtl_fm_cmd(freq_mhz, cfg, args)
    aplay_cmd = build_aplay_cmd(cfg, args)

    print(
        f"\n🎧 Playing {freq_mhz:.4f} MHz | "
        f"Mode: {cfg.mode.upper()} | "
        f"Audio: {cfg.audio_rate} Hz"
    )
    print("Press Enter to stop and return to scanner.")
    print("If you are using SSH, audio will play from the SDR machine/uConsole.\n")

    global current_audio_procs

    try:
        rtl_proc = subprocess.Popen(
            rtl_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        if rtl_proc.stdout is None:
            print("❌ Could not open rtl_fm audio stream.")
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

        input()

    except KeyboardInterrupt:
        print()

    finally:
        stop_audio()
        print("🔁 Stopped audio. Back to scanner.")


# ================== UI ==================

def print_main_menu() -> None:
    print("\n🚀 RTL-SDR CLI Scanner Plus")
    print("Receive-only scanner. Use only with authorization.\n")

    for key, cfg in BANDS.items():
        print(f"{key} = {cfg.name}")
        print(
            f"    {cfg.low_mhz:.3f}-{cfg.high_mhz:.3f} MHz | "
            f"{cfg.step_khz:g} kHz | "
            f"{cfg.mode.upper()}"
        )
        if cfg.note:
            print(f"    Note: {cfg.note}")

    print("q = Quit")


def print_peaks(peaks: list[SignalPeak], args: argparse.Namespace) -> None:
    print("\n📊 Found Frequencies")

    if not peaks:
        print("   No active frequency found above threshold.")
        print("   Try:")
        print("     --gain 45")
        print("     --integration 5")
        print("     --threshold-offset 8")
        print("     --min-db -75")
        return

    for idx, peak in enumerate(peaks[: args.max_results], start=1):
        over = peak.db - peak.threshold_db
        bar = "█" * min(40, max(0, int(over / 1.5)))
        lock = " 🔒" if peak.protected_reason else ""

        print(
            f"  {idx:2d}. {peak.freq_mhz:10.4f} MHz  "
            f"{peak.db:6.1f} dB  "
            f"SNR~{peak.db - peak.noise_floor_db:5.1f} dB  "
            f"{bar}{lock}"
        )

        if peak.protected_reason:
            print(f"      Protected: {peak.protected_reason}")


def scanner_loop(cfg: BandConfig, args: argparse.Namespace) -> bool:
    while True:
        peaks = scan_band(cfg, args)
        print_peaks(peaks, args)

        print("\nChoose action:")
        print("  [number] = Play/listen to that frequency")
        print("  [Enter]  = Rescan")
        print("  b        = Back to band menu")
        print("  q        = Quit")

        choice = input("\n> ").strip().lower()

        if choice == "q":
            return False

        if choice == "b":
            return True

        if choice == "":
            continue

        if choice.isdigit():
            idx = int(choice) - 1

            visible_peaks = peaks[: args.max_results]

            if 0 <= idx < len(visible_peaks):
                selected = visible_peaks[idx]
                play_frequency(selected.freq_mhz, cfg, args)
            else:
                print("❌ Invalid number.")

            continue

        print("❌ Invalid input. Use number, Enter, b, or q.")


# ================== ARGUMENTS ==================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RTL-SDR CLI scanner with numbered frequency playback."
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
        default=DEFAULT_MIN_DB,
        help="Minimum absolute threshold. Default: -65",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help="Maximum displayed results. Default: 20",
    )

    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="RTL-SDR device index, example: --device 0",
    )

    parser.add_argument(
        "--audio-device",
        default=None,
        help="Optional ALSA output device, example: --audio-device plughw:0,0",
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

    parser.set_defaults(log=True)

    return parser.parse_args()


# ================== MAIN ==================

def main() -> None:
    args = parse_args()
    require_tools()

    while True:
        print_main_menu()
        choice = input("\nChoose band: ").strip().lower()

        if choice == "q":
            break

        cfg = BANDS.get(choice)

        if not cfg:
            print("❌ Invalid band.")
            continue

        keep_running = scanner_loop(cfg, args)

        if not keep_running:
            break

    stop_audio()
    print("\n👋 Done.")


if __name__ == "__main__":
    main()
