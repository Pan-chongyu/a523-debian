"""Stop the owned CPUfreq service and remove only its installed files."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
base = Path('/root/tzx-recovery/cpufreq-runtime')
before = json.loads((base / 'before.json').read_text())
installed = json.loads((base / 'installed.json').read_text())
assert set(before) == set(installed) == {'usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko',
                                       'usr/local/lib/tzx-cpufreq/runtime.py',
                                       'etc/systemd/system/tzx-cpufreq.service'}
for name, digest in installed.items():
    path = Path('/') / name
    assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
subprocess.run(['systemctl', 'disable', '--now', 'tzx-cpufreq.service'], check=True)
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
for name, record in before.items():
    path = Path('/') / name
    if record is None:
        path.unlink()
    else:
        data = (base / 'files' / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == record['sha256']
        path.write_bytes(data)
        path.chmod(record['mode'])
subprocess.run(['systemctl', 'daemon-reload'], check=True)
Path('/var/lib/tzx/cpufreq-runtime-installed.json').unlink(missing_ok=True)
os.sync()
print('CPUFREQ_RUNTIME_ROLLED_BACK_FIXED_480_MHZ', flush=True)
