"""Restore exact v2 qualification after the identified oversized allocation trial."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
root = Path('/var/lib/tzx')
backup = Path('/root/tzx-recovery/screen-doublebuffer')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state = json.loads((root/'screen-installed.json').read_text())
before = json.loads((backup/'before-state.json').read_text())
assert state == before and state['profile'] == 'screen-functions-2-vblank'
for name, item in state['files'].items():
    assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == item['sha256'], name
assert not (root/'screen-boot-pending.json').exists()
assert not (root/'dram-gpu-boot-pending.json').exists()
assert not Path('/run/systemd/system/tzx-display.service.d/99-screen-doublebuffer-trial.conf').exists()
revoked = json.loads((root/'dram-gpu-revoked.json').read_text())
original = Path('/root/tzx-recovery/screen-functions-v1/gpu-qualified').read_bytes()
assert revoked['boot_id'] == boot and revoked['previous'] == json.loads(original)
text = subprocess.check_output(['dmesg'], text=True)
assert 'mm/page_alloc.c:5340' in text
assert 'bring-up failed -12' in text
assert not any(v in text for v in ('Unable to handle kernel', 'Internal error: Oops'))
journal = subprocess.check_output(['journalctl', '-b', '-u', 'tzx-screen-doublebuffer-trial',
                                   '-u', 'tzx-display', '-o', 'cat', '--no-pager'], text=True)
assert 'Cannot allocate memory' in journal
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4608
for name, data in {'allocation-failed-dmesg.txt': text.encode(), 'allocation-failed-units.txt': journal.encode(),
                   'allocation-gpu-revoked.json': (root/'dram-gpu-revoked.json').read_bytes()}.items():
    with (backup/name).open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
path = root/'gpu-qualified'
assert not path.exists()
temp = path.with_suffix('.allocation-recover')
with temp.open('wb') as f:
    f.write(original)
    os.fchmod(f.fileno(), 0o600)
    f.flush()
    os.fsync(f.fileno())
temp.replace(path)
fd = os.open(root, os.O_DIRECTORY)
os.fsync(fd)
os.close(fd)
os.sync()
subprocess.run(['systemd-run', '--unit=tzx-screen-dma-recover-reboot', '--on-active=3s',
                '/usr/bin/systemctl', 'reboot'], check=True, timeout=10)
print('TZX_SCREEN_V2_RESTORED_EXACT_QUALIFICATION_REBOOT_SCHEDULED', flush=True)
