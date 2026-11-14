"""Record the live baseline and request one normal reboot of the staged screen order."""
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state = Path('/var/lib/tzx')
installed = json.loads((state/'screen-fast-installed.json').read_text())
assert 'restored' not in installed['state']
subprocess.run(['python3','/home/debian/install_screen_fast_boot.py','verify'],check=True,timeout=35)
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
health = json.loads((state/'screen-boot-health.json').read_text())
assert health['boot_id'] == boot and health['result'] == 'PASS'
assert not (state/'screen-boot-pending.json').exists() and not (state/'dram-gpu-boot-pending.json').exists()
for name in ('cpu-dvfs','gpu-performance','emmc-hs'):
    status = json.loads(Path('/run/tzx-'+name+'.json').read_text())
    assert status['boot_id'] == boot and status['state'] == 'active'
record = dict(previous_boot_id=boot, requested_unix=int(time.time()), normal_reboot=True,
    installed_files=installed['files'], screen_health=health,
    prior_screen_fast_qualification=json.loads((state/'screen-fast-qualified.json').read_text())
        if (state/'screen-fast-qualified.json').exists() else None)
(state/'screen-fast-reboot-request.json').write_text(json.dumps(record,indent=2)+'\n')
os.sync()
print('SCREEN_FAST_NORMAL_REBOOT_REQUESTED',boot,flush=True)
subprocess.run(['systemd-run','--unit=tzx-screen-fast-reboot-'+str(int(time.time())),
    '--on-active=3s','/usr/bin/systemctl','reboot'],check=True,timeout=15)
