"""Summarize a real scan without publishing nearby SSIDs or BSSIDs."""
import collections
import json
from pathlib import Path
import re
import subprocess

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
text = Path('/home/debian/wifi-first-scan.txt').read_text()
frequencies = [int(value) for value in re.findall(r'^\s*freq: (\d+)', text, re.M)]
signals = [float(value) for value in re.findall(r'^\s*signal: (-?[\d.]+) dBm', text, re.M)]
report = {
    'bss_count': len(re.findall(r'^BSS ', text, re.M)),
    'frequency_counts': dict(sorted(collections.Counter(frequencies).items())),
    'bss_2_4ghz': sum(2400 <= value < 2500 for value in frequencies),
    'bss_5ghz': sum(5000 <= value < 5900 for value in frequencies),
    'strongest_signal_dbm': max(signals) if signals else None,
    'weakest_signal_dbm': min(signals) if signals else None,
    'sdio_clock_hz': int(Path('/sys/kernel/debug/mmc1/clock').read_text()),
    'sdio_error_counters': Path('/sys/kernel/debug/mmc1/err_stats').read_text(),
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'link': subprocess.check_output(['iw', 'dev', 'wlan0', 'link'], text=True).strip(),
}
assert report['bss_count'] == len(frequencies) and frequencies, 'No actual access points received'
print(json.dumps(report, indent=2))
