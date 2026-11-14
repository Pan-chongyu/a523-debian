#!/usr/bin/python3
"""Boot-only overrides for the isolated translation-format diagnostic."""
import os
import sys
from pathlib import Path

if os.uname().release != '7.3.3-tzx-a523-va48':
    raise SystemExit(0)
if Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() != '3e01ff55454d20202010209170281b59':
    raise SystemExit(1)
changes = {
    'lightdm.service': ['[Unit]', 'ConditionKernelVersion=7.3.3-tzx-a523-accel1'],
    'tzx-cpufreq.service': ['[Unit]', 'ConditionKernelVersion=7.3.3-tzx-a523-accel1'],
    'tzx-rtc-log.service': ['[Service]', 'ExecStart=',
        'ExecStart=/usr/bin/python3 /usr/local/lib/tzx-va48/rtc/runtime.py'],
}
for name, lines in changes.items():
    target = Path(sys.argv[1]) / (name + '.d')
    target.mkdir(parents=True, exist_ok=True)
    (target/'90-tzx-va48.conf').write_text(chr(10).join(lines) + chr(10))
