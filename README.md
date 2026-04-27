# RTL-SDR CLI Scanner Plus

**Author:** Aung Myat Thu

A receive-only RTL-SDR CLI scanner for authorized RF assessment, radio learning, signal discovery, and red-team reporting.

The scanner uses `rtl_power` to scan frequency ranges, detects active frequencies using a dynamic noise-floor threshold, displays found frequencies with numbers, and lets you choose a frequency to play audio directly from the command line using `rtl_fm` and `aplay`.

> This project is passive and receive-only. It does not transmit, decrypt, jam, spoof, replay, interfere with, or modify any radio communication.

---

## Table of Contents

- [Features](#features)
- [Legal and Safety Notice](#legal-and-safety-notice)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [CLI Workflow](#cli-workflow)
- [Command Examples](#command-examples)
- [CLI Options](#cli-options)
- [Band Configuration](#band-configuration)
- [CSV Logs](#csv-logs)
- [Recommended Settings](#recommended-settings)
- [Audio Output Notes](#audio-output-notes)
- [Troubleshooting](#troubleshooting)
- [Good Testing Practice](#good-testing-practice)
- [Example Report Finding](#example-report-finding)
- [Project Structure](#project-structure)
- [Limitations](#limitations)
- [Disclaimer](#disclaimer)
- [Author](#author)

---

## Features

- Multi-band RTL-SDR scanning
- Numbered CLI frequency selection
- Play/listen to detected frequency by choosing a number
- FM broadcast radio scan profile
- Airband AM scan profile
- Authorized UHF land-mobile scan profile
- Authorized portable radio test scan profile
- Dynamic noise-floor detection
- Signal peak clustering to reduce duplicate nearby results
- Live audio playback using `rtl_fm` and `aplay`
- Proper audio process cleanup before rescanning
- CSV logging for reporting evidence
- Protected emergency frequency blocking
- CLI options for gain, PPM, threshold, device index, scan timing, log directory, and ALSA audio device
- Works on Linux, Raspberry Pi, ClockworkPi uConsole, and similar devices

---

## Legal and Safety Notice

Use this tool only where you have permission and authorization.

This tool is intended for:

- Educational SDR and radio learning
- RF security awareness
- Passive RF visibility checks
- Authorized airport, office, or facility RF surveys
- Internal red-team reporting
- Testing your own radio devices in a lab

Do not use this tool to:

- Monitor private communications without permission
- Record or redistribute sensitive radio traffic
- Attempt decryption or access-control bypass
- Transmit, jam, spoof, replay, or interfere with radio systems
- Scan outside your approved test scope
- Collect operational information from third-party systems without authorization

Emergency and protected frequencies such as aviation guard channels are blocked from interactive listening by default.

---

## How It Works

The scanner follows this flow:

```text
Choose band
   ↓
Run rtl_power scan
   ↓
Calculate noise floor
   ↓
Detect active frequencies above threshold
   ↓
Cluster nearby bins into clean signal peaks
   ↓
Show found frequencies with numbers
   ↓
Choose number to play audio
   ↓
Press Enter to stop audio and return to scanner
```

Audio playback flow:

```text
rtl_fm  →  raw audio stream  →  aplay
```

Important:

- `rtl_power` and `rtl_fm` cannot use the same RTL-SDR dongle at the same time.
- The script automatically stops audio before starting a new scan.
- When listening, press `Enter` to stop audio and return to the scanner.

---

## Requirements

### Hardware

- RTL-SDR USB dongle
- Suitable antenna for the target frequency range
- Linux machine, Raspberry Pi, or ClockworkPi uConsole
- Optional: powered USB hub for better dongle stability
- Optional: USB extension cable to move the SDR away from computer noise

### Software

Install required packages:

```bash
sudo apt update
sudo apt install rtl-sdr alsa-utils python3
```

Check that your RTL-SDR is detected:

```bash
rtl_test
```

If the device is busy or blocked by the DVB driver, you may need to blacklist the default Linux DVB driver.

Create blacklist config:

```bash
sudo nano /etc/modprobe.d/blacklist-rtl.conf
```

Add:

```text
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
```

Then reboot:

```bash
sudo reboot
```

---

## Installation

Clone or copy the script:

```bash
nano sdr_scanner_plus.py
```

Make it executable:

```bash
chmod +x sdr_scanner_plus.py
```

Run it:

```bash
python3 sdr_scanner_plus.py
```

Optional direct execution:

```bash
./sdr_scanner_plus.py
```

---

## Usage

Start the scanner:

```bash
python3 sdr_scanner_plus.py
```

You will see a menu similar to this:

```text
🚀 RTL-SDR CLI Scanner Plus
Receive-only scanner. Use only with authorization.

1 = FM Broadcast Radio
    87.500-108.000 MHz | 100 kHz | WBFM
    Note: Good beginner test band.
2 = Airband AM
    118.000-137.000 MHz | 25 kHz | AM
    Note: Use only where legal and authorized. Emergency guard frequency is blocked.
3 = Authorized UHF Land Mobile Range
    450.000-470.000 MHz | 12.5 kHz | FM
    Note: Confirm local frequency allocation and written test scope.
4 = Authorized Portable Radio Test Range
    462.000-468.000 MHz | 12.5 kHz | FM
    Note: Jurisdiction-specific. Use only inside approved scope.
q = Quit
```

Choose a band:

```text
Choose band: 1
```

After scanning, active frequencies will be listed with numbers:

```text
📊 Found Frequencies
   1.   100.0000 MHz   -30.5 dB  SNR~ 25.1 dB  ███████████████
   2.   103.2500 MHz   -36.8 dB  SNR~ 18.8 dB  █████████
   3.   105.7000 MHz   -41.2 dB  SNR~ 14.4 dB  ██████
```

Choose a number to play that frequency:

```text
> 1
```

The script will play audio through the local audio output:

```text
🎧 Playing 100.0000 MHz | Mode: WBFM | Audio: 48000 Hz
Press Enter to stop and return to scanner.
```

Press `Enter` to stop listening and return to scanner.

---

## CLI Workflow

Inside a selected band:

```text
[number] = Play/listen to that frequency
[Enter]  = Rescan
b        = Back to band menu
q        = Quit
```

Example:

```text
> 2
```

This plays the second detected frequency.

To stop playback:

```text
Press Enter
```

To rescan:

```text
Press Enter again from the scan menu
```

---

## Command Examples

### Default scan

```bash
python3 sdr_scanner_plus.py
```

### Stronger scan for weak signals

```bash
python3 sdr_scanner_plus.py --gain 45 --integration 5 --threshold-offset 8 --min-db -75
```

### Less noisy scan

```bash
python3 sdr_scanner_plus.py --gain 35 --integration 3 --threshold-offset 15 --min-db -55
```

### Use a specific RTL-SDR device

```bash
python3 sdr_scanner_plus.py --device 0
```

### Use a specific ALSA audio output device

First list audio devices:

```bash
aplay -l
```

Then run:

```bash
python3 sdr_scanner_plus.py --audio-device plughw:0,0
```

### Disable CSV logging

```bash
python3 sdr_scanner_plus.py --no-log
```

### Custom log directory

```bash
python3 sdr_scanner_plus.py --log-dir ./reports/rf_scan_logs
```

---

## CLI Options

| Option | Description | Default |
|---|---|---:|
| `--gain` | RTL-SDR gain value | `40` |
| `--ppm` | PPM frequency correction | `0` |
| `--integration` | `rtl_power` scan integration time in seconds | `2` |
| `--threshold-offset` | dB above median noise floor | `12` |
| `--min-db` | Minimum absolute active threshold | `-65` |
| `--max-results` | Maximum displayed signal peaks | `20` |
| `--device` | RTL-SDR device index | Auto/default |
| `--audio-device` | Optional ALSA output device, example `plughw:0,0` | Default ALSA output |
| `--log-dir` | Directory for CSV logs | `./sdr_logs` |
| `--no-log` | Disable CSV logging | Logging enabled |

---

## Band Configuration

The default script includes these scan profiles:

| Band | Range | Step | Mode | Purpose |
|---|---:|---:|---|---|
| FM Broadcast Radio | `87.5-108 MHz` | `100 kHz` | WBFM | Beginner testing and broadcast radio learning |
| Airband AM | `118-137 MHz` | `25 kHz` | AM | Aviation receive-only survey where legal and authorized |
| Authorized UHF Land Mobile | `450-470 MHz` | `12.5 kHz` | FM | Authorized UHF RF assessment |
| Authorized Portable Radio Test | `462-468 MHz` | `12.5 kHz` | FM | Authorized portable radio testing |

You should adjust these ranges based on your country, client authorization, and local frequency allocation.

---

## CSV Logs

By default, scan results are saved to:

```text
./sdr_logs/active_signals.csv
```

Example CSV fields:

```csv
timestamp,band,frequency_mhz,mode,db,noise_floor_db,threshold_db,protected_reason
```

This is useful for:

- Red-team evidence
- RF survey reports
- Repeated scan comparison
- Signal strength analysis
- Location-based testing notes
- Educational lab notes

Example:

```bash
cat sdr_logs/active_signals.csv
```

---

## Detection Logic

The scanner uses `rtl_power` to scan a frequency range.

Instead of relying only on a fixed threshold, it calculates the local noise floor:

```text
noise_floor = median signal level
active_threshold = max(noise_floor + threshold_offset, min_db)
```

A frequency bin is considered active when:

```text
signal_db >= active_threshold
```

Then nearby active bins are clustered so one real signal does not appear as too many duplicate results.

---

## Recommended Settings

### Beginner FM radio test

```bash
python3 sdr_scanner_plus.py --gain 35 --integration 2 --threshold-offset 10
```

### Indoor testing

```bash
python3 sdr_scanner_plus.py --gain 35 --integration 3 --threshold-offset 12
```

### Outdoor testing

```bash
python3 sdr_scanner_plus.py --gain 40 --integration 3 --threshold-offset 10
```

### Weak signal search

```bash
python3 sdr_scanner_plus.py --gain 45 --integration 5 --threshold-offset 8 --min-db -75
```

### Noisy RF environment

```bash
python3 sdr_scanner_plus.py --gain 30 --integration 5 --threshold-offset 18 --min-db -50
```

---

## Audio Output Notes

### Local machine

If you run the script directly on your laptop, Raspberry Pi, or uConsole, audio plays from that device.

### SSH session

If you SSH into the uConsole or Raspberry Pi and run the script there, `aplay` plays audio on the remote device, not your SSH laptop.

Example:

```bash
ssh user@uconsole
python3 sdr_scanner_plus.py
```

Audio will play from the uConsole audio output.

### Choose ALSA device

List audio devices:

```bash
aplay -l
```

Use a specific device:

```bash
python3 sdr_scanner_plus.py --audio-device plughw:0,0
```

---

## Troubleshooting

### `rtl_power failed`

Possible reasons:

- RTL-SDR is not connected
- Another process is using the dongle
- Permission issue
- DVB driver is using the device
- Bad USB cable or weak power
- Incorrect device index

Check:

```bash
rtl_test
```

Kill existing SDR processes:

```bash
pkill rtl_fm
pkill rtl_power
pkill rtl_tcp
```

Reconnect the RTL-SDR and try again.

---

### `usb_claim_interface error`

This usually means the kernel DVB driver is using the dongle.

Fix by blacklisting the DVB driver:

```bash
sudo nano /etc/modprobe.d/blacklist-rtl.conf
```

Add:

```text
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
```

Reboot:

```bash
sudo reboot
```

---

### No audio when playing frequency

Install ALSA tools:

```bash
sudo apt install alsa-utils
```

Test speaker:

```bash
speaker-test -t wav -c 2
```

Check audio devices:

```bash
aplay -l
```

Try a specific device:

```bash
python3 sdr_scanner_plus.py --audio-device plughw:0,0
```

---

### Audio plays on uConsole instead of SSH laptop

This is expected.

When you run `aplay` on the uConsole, audio plays on the uConsole.

For remote listening, consider authorized alternatives such as:

- Running GUI SDR locally on the device
- Using `rtl_tcp` over trusted network
- Using VPN or SSH tunnel for remote SDR access
- Using proper network audio setup

Do not expose `rtl_tcp` directly to the internet.

---

### Too many false positives

Use a higher threshold offset:

```bash
python3 sdr_scanner_plus.py --threshold-offset 18
```

Or lower the gain:

```bash
python3 sdr_scanner_plus.py --gain 30
```

---

### Cannot detect weak signals

Try:

```bash
python3 sdr_scanner_plus.py --gain 45 --integration 5 --threshold-offset 8 --min-db -75
```

Also check:

- Antenna type
- Antenna placement
- USB noise
- RTL-SDR gain
- Distance from transmitter
- Whether the signal is active during scan time
- Whether your selected band is correct

---

### Frequency looks slightly wrong

Your RTL-SDR may need PPM correction.

Try small values:

```bash
python3 sdr_scanner_plus.py --ppm 1
python3 sdr_scanner_plus.py --ppm -1
```

For better calibration, compare against a known strong broadcast station.

---

## Good Testing Practice

For a professional RF assessment, record:

- Test date and time
- Test location
- Authorization/scope reference
- Antenna used
- SDR dongle model
- Gain setting
- PPM setting
- Frequency range
- Detected active frequencies
- Signal strength
- Noise floor
- Estimated SNR
- Whether the frequency is inside approved scope
- Screenshots or CSV logs
- Risk rating
- Recommendation

Example report note:

```text
During passive receive-only RF assessment, active signals were observed within the approved scan range. No transmission, interference, replay, decryption, or access bypass was performed. Results are based on signal presence and strength only.
```

---

## Example Report Finding

```text
Finding: Unidentified Active UHF Signal Detected

Frequency: 462.5625 MHz
Signal Strength: -34.8 dB
Noise Floor: -55.2 dB
Estimated SNR: 20.4 dB
Threshold: -43.2 dB
Mode Tested: FM receive-only
Impact: Unknown active radio communication was detected within the approved survey range.
Recommendation: Validate whether this frequency belongs to authorized staff radios, contractor radios, or unrelated external sources. Maintain an approved frequency inventory.
Testing Limitation: No transmission, interference, decryption, replay, or access bypass was performed.
```

---

## Project Structure

```text
.
├── sdr_scanner_plus.py
├── README.md
└── sdr_logs/
    └── active_signals.csv
```

---

## Suggested `.gitignore`

```gitignore
# SDR scan logs
sdr_logs/
*.csv

# Python
__pycache__/
*.pyc
.venv/
venv/

# Local notes
*.log
.DS_Store
```

If you want to commit sample CSV evidence, remove `*.csv` and commit only sanitized files.

---

## Git Commit

After updating the script and README:

```bash
git status
git add sdr_scanner_plus.py README.md
git commit -m "Upgrade SDR scanner with numbered CLI playback"
```

Push current branch:

```bash
git push origin "$(git branch --show-current)"
```

---

## Limitations

- RTL-SDR is receive-only
- Cannot transmit
- Cannot decode encrypted communication
- Cannot identify users automatically
- Cannot prove ownership of a signal without additional validation
- Signal strength depends heavily on antenna and location
- Frequency allocation depends on country and local regulation
- Audio playback depends on ALSA configuration
- `rtl_power` scanning may miss short transmissions if the integration time is too short

---

## Disclaimer

This project is for authorized, educational, and defensive RF assessment only.

The author is not responsible for misuse of this tool.
Always follow local laws, organizational policy, and written test scope.

---

## Author

**Aung Myat Thu**

Cybersecurity and software engineering practitioner focused on security testing, automation, backend engineering, SDR learning, and red-team education.
