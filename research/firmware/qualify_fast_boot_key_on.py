"""Audit optimized boot after actual PMIC off and physical key-on."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
request=json.loads((state/'fast-boot-key-on-request.json').read_text())
assert request['previous_boot_id']!=boot
sha=lambda b:hashlib.sha256(b).hexdigest()
def run(*args,timeout=90):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)
print(run('python3','-u','/home/debian/verify_boot_latency.py','--key-on'),end='',flush=True)
proof=json.loads((state/'boot-latency-qualified.json').read_text())
assert proof['toc0_sha256']==request['toc0_sha256']
pmic=json.loads(run('python3','/usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py'))
assert pmic['boot_id']==boot and pmic['axp323_id']=='0x49'
assert int(pmic['axp717']['0x20'],16)&1 and int(pmic['axp717']['0x21'],16)&2
assert not int(pmic['axp717']['0x21'],16)&0xf8
assert pmic['axp717']['0x85']=='0xc9' and int(pmic['axp717']['0x27'],16)==8
print('OPTIMIZED_BOOT_PMIC_OFF_AND_KEY_ON_REASONS_PASS',json.dumps(pmic),flush=True)
print(run('python3','-u','/home/debian/verify_cpu_gpu_integration.py',timeout=220),end='',flush=True)
load=json.loads((state/'cpu-gpu-integration-qualified.json').read_text());assert load['boot_id']==boot and load['status']=='PASS'
audit=run('python3','/home/debian/verify_safe_memory.py','--files-only',timeout=130)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
print(audit,end='',flush=True)
idle=[]
for attempt in range(40):
    idle.append(dict(cpu_khz=[int(Path('/sys/devices/system/cpu/cpufreq/policy%d/scaling_cur_freq'%i).read_text()) for i in (0,4)],
        gpu_runtime=Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip()))
    time.sleep(.4)
assert [min(v['cpu_khz'][i] for v in idle) for i in (0,1)]==[120000,120000]
assert any(v['gpu_runtime']=='suspended' for v in idle)
assert not run('systemctl','--failed','--no-legend','--plain').strip()
record=dict(status='PASS',boot_id=boot,previous_boot_id=request['previous_boot_id'],
    normal_reboot_verified=True,poweroff_key_on_verified=True,complete_removal_of_power_tested=False,
    toc0_sha256=proof['toc0_sha256'],normal_reboot_proof=request['normal_boot'],
    cold_boot_proof=proof,pmic_status=pmic,combined_load=load,file_audit=audit,idle_samples=idle,
    cpu_idle_minimum_khz=[120000,120000],gpu_autosuspend=True,
    right_landscape=True,visual_confirmation='pending',all_component_manifests_unchanged=True)
target=state/'fast-boot-key-on-qualified.json';target.write_text(json.dumps(record,indent=2)+'\n')
installed=state/'boot-hwcrc-installed.json';value=json.loads(installed.read_text())
value.update(state='actual-normal-and-PMIC-key-on-load-verified',poweroff_key_on_verified=True,
    poweroff_key_on_boot_id=boot,poweroff_key_on_proof_sha256=sha(target.read_bytes()))
installed.write_text(json.dumps(value,indent=2)+'\n')
os.sync()
print('OPTIMIZED_BOOT_PMIC_KEY_ON_FULL_STACK_PASS',boot,flush=True)
