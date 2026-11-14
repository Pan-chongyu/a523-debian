"""Attach the user's actual screen/touch observations and accurate boot provenance."""
import hashlib
import json
import os
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='552e50af-434d-4ef7-8206-46b6d77202ca'
sha=lambda b:hashlib.sha256(b).hexdigest()
target=state/'fast-boot-key-on-qualified.json';proof=json.loads(target.read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot and proof['poweroff_key_on_verified']
assert proof['previous_boot_id']=='e6cf9178-a7c0-410e-86aa-d534ce52e0fa'
proof['visual_confirmation']=dict(normal_reboot_black_screen_seconds_approx=28,
    physical_key_to_visible_screen_seconds_approx=31,right_landscape=True,touch_and_desktop='user-confirmed normal')
proof['cold_boot_proof']['verification_method']='PMIC-key-on'
proof['normal_reboot_proof']['verification_method']='normal-reboot'
proof['cold_boot_proof']['visual_confirmation']=dict(physical_key_to_visible_screen_seconds_approx=31,
    right_landscape=True,touch_and_desktop='user-confirmed normal')
proof['normal_reboot_proof']['visual_confirmation']=dict(black_screen_seconds_approx=28,
    right_landscape=True,touch_and_desktop='user-confirmed normal')
target.write_text(json.dumps(proof,indent=2)+'\n')
path=state/'boot-latency-qualified.json';value=json.loads(path.read_text())
assert value['boot_id']==boot
value.update(verification_method='PMIC-key-on',visual_confirmation=proof['visual_confirmation'],
    poweroff_key_on_for_fast_crc='PASS')
path.write_text(json.dumps(value,indent=2)+'\n')
path=state/'boot-latency-installed.json';value=json.loads(path.read_text())
assert value['verified_boot_id']==boot
value.update(state='actual-normal-and-PMIC-key-on-order-verified',
    normal_reboot_boot_id=proof['previous_boot_id'],poweroff_key_on_boot_id=boot,
    normal_reboot_verified=True,poweroff_key_on_verified=True)
path.write_text(json.dumps(value,indent=2)+'\n')
path=state/'boot-hwcrc-installed.json';value=json.loads(path.read_text())
value.update(state='actual-normal-and-PMIC-key-on-load-verified',
    normal_reboot_verified=True,normal_reboot_boot_id=proof['previous_boot_id'],
    poweroff_key_on_verified=True,poweroff_key_on_boot_id=boot,poweroff_key_on_proof_sha256=sha(target.read_bytes()))
path.write_text(json.dumps(value,indent=2)+'\n')
path=state/'performance-clean-shutdown.json';value=json.loads(path.read_text())
assert sha((state/'cpu-full-qualified.json').read_bytes())==value['restored_exact_CPU_qualification_sha256']
value.update(normal_reboot_verification='PASS',verified_boot_id=proof['previous_boot_id'],
    poweroff_key_on_verification='PASS',poweroff_key_on_boot_id=boot,
    CPU_qualification_preserved=True,all_three_supervisors_automatically_active=True)
path.write_text(json.dumps(value,indent=2)+'\n')
os.sync()
print('OPTIMIZED_BOOT_USER_SCREEN_TOUCH_AND_BOOT_PROVENANCE_RECORDED',boot,flush=True)
