"""Request one controlled early-screen boot while preserving prior trial evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

assert os.geteuid()==0 and sys.argv[1:] in (['reboot'],['poweroff'])
action=sys.argv[1]
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
installed=json.loads((state/'boot-panel-installed.json').read_text())
assert 'restored' not in installed['state']
subprocess.run(['python3',installed.get('installer','/home/debian/install_boot_panel.py'),
    'verify',installed['toc0_sha256']],check=True,timeout=45)
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
screen=json.loads((state/'screen-boot-health.json').read_text())
assert screen['boot_id']==boot and screen['result']=='PASS'
assert not (state/'screen-boot-pending.json').exists() and not (state/'dram-gpu-boot-pending.json').exists()
for name in ('cpu-dvfs','gpu-performance','emmc-hs'):
    value=json.loads(Path('/run/tzx-'+name+'.json').read_text())
    assert value['boot_id']==boot and value['state']=='active'
if action=='poweroff':
    proof=json.loads((state/'boot-panel-qualified.json').read_text())
    assert proof['boot_id']==boot and proof['status']=='PASS' and proof['early_panel_success']
    assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip()=='Y'
path=state/'boot-panel-trial-request.json'
if path.exists():
    saved=state/('boot-panel-trial-request-before-'+str(int(time.time()))+'.json')
    assert not saved.exists()
    saved.write_bytes(path.read_bytes())
record=dict(previous_boot_id=boot,action=action,requested_unix=int(time.time()),
    toc0_sha256=installed['toc0_sha256'],previous_screen_health=screen,
    prior_early_panel_proof=json.loads((state/'boot-panel-qualified.json').read_text())
        if (state/'boot-panel-qualified.json').exists() else None)
path.write_text(json.dumps(record,indent=2)+'\n')
os.sync()
print('EARLY_PANEL_REAL_BOOT_REQUESTED',json.dumps(dict(action=action,previous_boot_id=boot)),flush=True)
subprocess.run(['systemd-run','--unit=tzx-boot-panel-'+action+'-'+str(int(time.time())),
    '--on-active=3s','/usr/bin/systemctl',action],check=True,timeout=15)
