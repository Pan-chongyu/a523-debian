"""Validate the actual optimized normal boot before normal PMIC shutdown."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
target=state/'fast-boot-key-on-request.json';assert not target.exists()
sha=lambda b:hashlib.sha256(b).hexdigest()
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=90)
print(run('python3','-u','/home/debian/verify_boot_latency.py'),end='',flush=True)
proof=json.loads((state/'boot-latency-qualified.json').read_text())
assert proof['boot_id']==boot and proof['status']=='PASS'
assert proof['toc0_sha256']=='50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b'
assert proof['boot_8bit_verified'] and proof['IEEE_hardware_CRC32_all_sectors_verified'][3]==29314
installed=json.loads((state/'pmic-poweroff-installed.json').read_text())
assert installed['poweroff_tested'] and installed['unit_enabled']
for name,digest in installed['files'].items():assert sha(Path('/'+name).read_bytes())==digest,name
assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip()=='Y'
record=dict(state='qualified-optimized-normal-boot-PMIC-off-requested',previous_boot_id=boot,
    requested_unix=int(time.time()),normal_boot_proof_sha256=sha((state/'boot-latency-qualified.json').read_bytes()),
    toc0_sha256=proof['toc0_sha256'],normal_boot=proof,physical_key_on_required=True,
    method='systemctl poweroff then physical power key; battery and USB attached')
with target.open('w') as f:
    json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
os.sync()
print('FAST_BOOT_PMIC_OFF_PHYSICAL_KEY_ON_REQUESTED',boot,flush=True)
print(run('systemd-run','--unit=tzx-fast-boot-key-on-test','--on-active=3s','/usr/bin/systemctl','poweroff'),flush=True)
