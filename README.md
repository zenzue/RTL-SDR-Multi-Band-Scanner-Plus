# RTL-SDR Multi-Band Scanner Plus

**Author:** Aung Myat Thu

A receive-only RTL-SDR scanner for authorized RF assessment, signal discovery, and red-team reporting.  
This tool uses `rtl_power` for scanning and `rtl_fm` with `aplay` for live audio monitoring.

> This project is designed for passive, receive-only testing. It does not transmit, decrypt, jam, interfere with, or modify any radio communication.

---

## Features

- Multi-band RTL-SDR scanning
- Airband AM scanning support
- UHF land-mobile / portable radio range scanning
- Dynamic noise-floor detection
- Signal peak clustering to reduce duplicate nearby results
- Live listen mode with proper process cleanup
- CSV logging for reporting evidence
- Protected emergency frequency blocking
- CLI options for gain, PPM, threshold, device index, and scan timing
- Works well on Linux, Raspberry Pi, ClockworkPi uConsole, and similar devices

---

## Legal and Safety Notice

Use this tool only where you have authorization.

This tool is intended for:

- RF security assessment
- Educational SDR testing
- Authorized airport, office, or facility RF surveys
- Passive signal visibility checks
- Internal red-team reporting

Do not use this tool to:

- Monitor private communications without permission
- Record or redistribute sensitive radio traffic
- Attempt decryption or bypass access controls
- Transmit, jam, spoof, or interfere with radio systems
- Scan outside your approved test scope

Emergency and protected frequencies such as aviation guard channels are blocked from interactive listening by default.

---

## Requirements

### Hardware

- RTL-SDR USB dongle
- Suitable antenna for the target frequency range
- Linux machine, Raspberry Pi, or uConsole
- Optional: powered USB hub for better dongle stability

### Software

Install required packages:

```bash
sudo apt update
sudo apt install rtl-sdr alsa-utils python3
````

Check that your RTL-SDR is detected:

```bash
rtl_test
```

If the device is busy or blocked by the DVB driver, you may need to blacklist the default driver.

Create blacklist config:

```bash
sudo nano /etc/modprobe.d/blacklist-rtl.conf
```

Add:

```bash
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

---

## Usage

Start the scanner:

```bash
python3 sdr_scanner_plus.py
```

You will see a menu like this:

```text
1 = Airband AM, authorized receive-only scan
2 = Authorized UHF land-mobile range
3 = Authorized portable-radio test range
q = quit
```

Choose a band:

```text
Choose band: 1
```

After scanning, active signals will be listed:

```text
1. 125.5000 MHz   -35.2 dB   +14.5 over threshold
2. 130.7000 MHz   -39.8 dB   +9.9 over threshold
```

Options:

```text
[ number ] = Listen
[ Enter ]  = Rescan
[ b ]      = Change band
[ q ]      = Quit
```

To listen to a detected frequency, enter the number:

```text
> 1
```

Press `Enter` or `Ctrl+C` to stop listening and return to scanning.

---

## Command Examples

### Default scan

```bash
python3 sdr_scanner_plus.py
```

### Stronger scan for weak signals

```bash
python3 sdr_scanner_plus.py --gain 45 --integration 5 --threshold-offset 8 --min-db -70
```

### Less noisy scan

```bash
python3 sdr_scanner_plus.py --gain 35 --integration 3 --threshold-offset 15 --min-db -55
```

### Use specific RTL-SDR device

```bash
python3 sdr_scanner_plus.py --device 0
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

| Option               | Description                       | Default         |
| -------------------- | --------------------------------- | --------------- |
| `--gain`             | RTL-SDR gain value                | `40`            |
| `--ppm`              | PPM frequency correction          | `0`             |
| `--integration`      | Scan integration time in seconds  | `2`             |
| `--threshold-offset` | dB above median noise floor       | `12`            |
| `--min-db`           | Minimum absolute signal threshold | `-60`           |
| `--max-results`      | Maximum listed signal peaks       | `15`            |
| `--log-dir`          | Directory for CSV logs            | `./sdr_logs`    |
| `--no-log`           | Disable CSV logging               | Logging enabled |
| `--device`           | RTL-SDR device index              | Auto/default    |

---

## Band Configuration

The default script includes these scan profiles:

| Band                 |         Range |       Step | Mode | Purpose                           |
| -------------------- | ------------: | ---------: | ---- | --------------------------------- |
| Airband              | `118-137 MHz` |   `25 kHz` | AM   | Aviation receive-only survey      |
| UHF Land Mobile      | `450-470 MHz` | `12.5 kHz` | FM   | Authorized UHF assessment         |
| Portable Radio Range | `462-468 MHz` | `12.5 kHz` | FM   | Authorized portable radio testing |

You should adjust these ranges based on your country, client authorization, and local frequency allocation.

---

## CSV Logs

By default, scan results are saved to:

```text
./sdr_logs/active_signals.csv
```

Example CSV fields:

```csv
timestamp,band_key,band_name,freq_mhz,db,noise_floor_db,threshold_db,protected_reason
```

This is useful for:

* Red-team evidence
* RF survey reports
* Repeated scan comparison
* Signal strength analysis
* Location-based testing notes

Example:

```bash
cat sdr_logs/active_signals.csv
```

---

## How Detection Works

The scanner uses `rtl_power` to scan a frequency range.

Instead of using only a fixed threshold, it calculates:

```text
noise_floor = median signal level
active_threshold = noise_floor + threshold_offset
```

A frequency is considered active when:

```text
signal_db >= active_threshold
```

This helps reduce false positives in noisy environments.

---

## Recommended Settings

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

## Troubleshooting

### `rtl_power failed`

Possible reasons:

* RTL-SDR is not connected
* Another process is using the dongle
* Permission issue
* DVB driver is using the device
* Bad USB cable or weak power

Check:

```bash
rtl_test
```

Kill existing SDR processes:

```bash
pkill rtl_fm
pkill rtl_power
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

```bash
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
```

Reboot:

```bash
sudo reboot
```

---

### No audio when listening

Install ALSA tools:

```bash
sudo apt install alsa-utils
```

Test audio:

```bash
speaker-test -t wav -c 2
```

Check audio devices:

```bash
aplay -l
```

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

* Antenna type
* Antenna placement
* USB noise
* RTL-SDR gain
* Distance from transmitter
* Whether the signal is active during scan time

---

## Good Testing Practice

For a professional RF assessment, record:

* Test date and time
* Test location
* Antenna used
* SDR dongle model
* Gain setting
* Frequency range
* Detected active frequencies
* Signal strength
* Whether the frequency is inside approved scope
* Screenshots or CSV logs
* Risk rating
* Recommendation

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
Threshold: -43.2 dB
Mode Tested: FM receive-only
Impact: Unknown active radio communication was detected within the approved survey range.
Recommendation: Validate whether this frequency belongs to authorized staff radios, contractor radios, or unrelated external sources. Maintain an approved frequency inventory.
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

## Limitations

* RTL-SDR is receive-only
* Cannot transmit
* Cannot decode encrypted communication
* Cannot identify users automatically
* Cannot prove ownership of a signal without additional validation
* Signal strength depends heavily on antenna and location
* Frequency allocation depends on country and local regulation

---

## Disclaimer

This project is for authorized, educational, and defensive RF assessment only.

The author is not responsible for misuse of this tool.
Always follow local laws, organizational policy, and written test scope.

---

## Author

**Aung Myat Thu**

Cybersecurity and software engineering practitioner focused on security testing, automation, backend engineering, and red-team learning.
