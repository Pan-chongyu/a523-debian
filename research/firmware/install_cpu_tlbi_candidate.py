"""Install the single-option A55 workaround candidate with a checked #3 rollback."""
import hashlib
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#3 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
old = '4044fd37e59399ab338d6892b4ee37c47d48f9e82709b24f25fc07152fe6058b'
new = '32648d80d699892b3dcfe0be37fdc07a5ed30d95d8b9ad8cf2140bb6f3181799'
new_config = 'd1b48cb2fd4a06cc02a188bc79aefeb63425dd27ad3b46896226e3061c0653ae'
size = 14809088
with open('/dev/mmcblk0', 'rb', buffering=0) as emmc:
    emmc.seek(4096*512)
    before = emmc.read(size)
assert hashlib.sha256(before).hexdigest() == old
assert hashlib.sha256(Path('/home/debian/linux-bundle.bin').read_bytes()).hexdigest() == new
config = Path('/home/debian/cpu-tlbi-kernel.config').read_bytes()
assert hashlib.sha256(config).hexdigest() == new_config
backup = Path('/root/tzx-recovery/gpu-clockfix')
backup.mkdir(parents=True, exist_ok=True)
target = backup/'bundle-before-cpu-tlbi.bin'
if not target.exists():
    with target.open('wb') as stream:
        stream.write(before)
        stream.flush()
        os.fsync(stream.fileno())
assert hashlib.sha256(target.read_bytes()).hexdigest() == old
original_config = backup/'config-before-cpu-tlbi'
current_config = Path('/boot/config-7.3.3-tzx-a523-accel1')
if not original_config.exists():
    original_config.write_bytes(current_config.read_bytes())
subprocess.run(['sh', '/home/debian/update-cpu-tlbi-bundle.sh'], check=True, timeout=90)
current_config.write_bytes(config)
os.sync()
print('CPU_TLBI_CANDIDATE_INSTALLED_CHECKED_ROLLBACK_RETAINED', flush=True)
subprocess.run(['systemd-run', '--unit=tzx-cpu-tlbi-candidate-reboot', '--on-active=3s',
                '/usr/bin/systemctl', 'reboot'], check=True)
