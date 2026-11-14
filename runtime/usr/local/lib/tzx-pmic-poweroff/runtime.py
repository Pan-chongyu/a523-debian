"""Load the guarded soft-off handler; never issue power-off from this helper."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

def read_exact_board_toc0(fd):
    head = os.pread(fd, 32, 256*512)
    assert len(head) == 32 and head[:8] == b'TOC0.GLH'
    length = int.from_bytes(head[28:32], 'little')
    assert length in (40960, 49152)
    data = os.pread(fd, length, 256*512)
    assert len(data) == length
    return data

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('verify', 'start', 'remove'))
a = p.parse_args()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
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
    assert hashlib.sha256(read_exact_board_toc0(fd)).hexdigest() in ('311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75', '4d1b90298dfc6238ea579eab33f7ca168639f5c512c9bddfeb61c1764118c842', '70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0', '4ae89856592e7b95fde5d0b40e49a09255f9745470fa9cc22bc64a06319ac4bc', '319cdcc46804ce7136b5f00479dd6c320bc561340ea285655293de3665ab179e', '50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b', '1c2ce9324aae67cf5747c36249db0785c74d52c4094e4e735e37217f60800b41', '367d51b493c2c647e12cfb24264afcac714cebcaa8b4605301620211f0befa1c', '09f4028fff214369e301e087c59d4c1dc359e0ee774e19556e73aa867845b0ca')
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
