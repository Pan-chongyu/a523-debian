"""Preserve the real normal boot proof before a physical power-key screen test."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
state = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
target = state/'screen-fast-key-on-request.json'
assert not target.exists()
sha = lambda b: hashlib.sha256(b).hexdigest()
subprocess.run(['python3','/home/debian/install_screen_fast_boot.py','verify'],check=True,timeout=45)
proof = json.loads((state/'screen-fast-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot and proof['normal_reboot_verified']
assert proof['verification_method'] == 'normal-reboot'
assert proof['unchanged_native_stack']['toc0_sha256'] == '50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b'
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
installed = json.loads((state/'pmic-poweroff-installed.json').read_text())
assert installed['poweroff_tested'] and installed['unit_enabled']
for name,digest in installed['files'].items():
    assert sha(Path('/'+name).read_bytes()) == digest, name
assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() == 'Y'
assert not (state/'screen-boot-pending.json').exists() and not (state/'dram-gpu-boot-pending.json').exists()
record = dict(previous_boot_id=boot,requested_unix=int(time.time()),
    normal_screen_proof=proof,physical_key_on_required=True,
    method='systemctl poweroff then physical power key; battery and USB remain attached',
    complete_removal_of_power_tested=False)
with target.open('w') as stream:
    json.dump(record,stream,indent=2)
    stream.write('\n')
    stream.flush()
    os.fsync(stream.fileno())
os.sync()
print('SCREEN_FAST_PMIC_OFF_PHYSICAL_KEY_ON_REQUESTED',boot,flush=True)
subprocess.run(['systemd-run','--unit=tzx-screen-fast-key-on-'+str(int(time.time())),
    '--on-active=3s','/usr/bin/systemctl','poweroff'],check=True,timeout=15)
