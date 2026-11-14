"""Load the guarded soft-off handler; never issue power-off from this helper."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('verify', 'start', 'remove'))
a = p.parse_args()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
root = Path('/usr/local/lib/tzx-pmic-poweroff')
module = root/'tzx_pmic_poweroff.ko'
assert hashlib.sha256(module.read_bytes()).hexdigest() == 'eabf81dae1d5cf430ad4791c0dacd625825e15690ffeff919caf7c59d0ff9af8'
assert int(Path('/proc/sys/kernel/tainted').read_text()) in (0, 4096)

if a.operation == 'remove':
    if Path('/sys/module/tzx_pmic_poweroff').exists():
        subprocess.run(['rmmod', 'tzx_pmic_poweroff'], check=True, timeout=15)
    print('TZX_PMIC_POWEROFF_HANDLER_REMOVED_WITHOUT_PMIC_WRITE', flush=True)
    raise SystemExit(0)

fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    assert hashlib.sha256(os.pread(fd, 40960, 256*512)).hexdigest() == '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
finally:
    os.close(fd)


def read_status():
    value = json.loads(subprocess.check_output(['python3', str(root/'read_pmic_shutdown_status.py')],
                                             text=True, timeout=20))
    assert value['axp323_id'] == '0x49' and value['axp717']['0x85'] == '0xc9'
    assert int(value['axp717']['0x27'], 16) & 0xf3 == 0
    return value


before = read_status()
if a.operation == 'start':
    assert not Path('/sys/module/tzx_pmic_poweroff').exists()
    subprocess.run(['insmod', str(module), 'armed=1'], check=True, timeout=20)
    assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() == 'Y'
    after = read_status()
    assert after['axp717']['0x27'] == before['axp717']['0x27']
    assert after['boot_id'] == before['boot_id']
    print('TZX_PMIC_POWEROFF_PREPARE_HANDLER_REGISTERED_NO_CONTROL_WRITE', json.dumps(after), flush=True)
else:
    print('TZX_PMIC_POWEROFF_HARDWARE_GUARD_PASS', json.dumps(before), flush=True)
