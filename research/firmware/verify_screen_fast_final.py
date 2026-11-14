"""Bounded coexistence and file-integrity checks on the final screen startup boot."""
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
state = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof = json.loads((state/'screen-fast-key-on-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot and proof['poweroff_key_on_verified']

def run(*args, timeout=90):
    output = subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)
    print(output,end='',flush=True)
    return output

run('python3','-u','/home/debian/verify_cpu_gpu_integration.py',timeout=220)
load = json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
assert load['status']=='PASS' and load['boot_id']==boot
audit = run('python3','/home/debian/verify_safe_memory.py','--files-only',timeout=140)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
samples = []
for _ in range(40):
    samples.append(dict(cpu_khz=[int(Path('/sys/devices/system/cpu/cpufreq/policy%d/scaling_cur_freq'%i).read_text())
        for i in (0,4)],gpu_runtime=Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip()))
    time.sleep(.4)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
run('python3','/home/debian/install_screen_fast_boot.py','verify')
record = dict(status='PASS',boot_id=boot,normal_reboot_verified=True,poweroff_key_on_verified=True,
    power_cycle_scope='PMIC-off then physical key; battery and USB connected',
    complete_removal_of_power_tested=False,screen_key_on_proof=proof,combined_load=load,
    file_audit=audit,idle_samples=samples,
    cpu_minimum_observed_khz=[min(s['cpu_khz'][i] for s in samples) for i in (0,1)],
    gpu_autosuspend_observed=any(s['gpu_runtime']=='suspended' for s in samples),
    scope='Bounded checks; does not establish long-term reliability')
(state/'screen-fast-final-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
os.sync()
print('SCREEN_FAST_FINAL_KEY_ON_LOAD_FILE_AUDIT_PASS',json.dumps(dict(boot_id=boot,
    seconds=load['seconds'],cpu_minimum_observed_khz=record['cpu_minimum_observed_khz'],
    gpu_autosuspend_observed=record['gpu_autosuspend_observed'])),flush=True)
