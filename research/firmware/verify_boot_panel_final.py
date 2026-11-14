"""Bounded full-stack checks after actual PMIC-off/key-on early panel boot."""
import json,os,subprocess,time
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'boot-panel-key-on-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot and proof['PMIC_key_on_verified']
assert proof['normal_reboot_proof']['status']=='PASS'
def run(*args,timeout=90):
    out=subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)
    print(out,end='',flush=True)
    return out
run('python3','-u','/home/debian/verify_cpu_gpu_integration.py',timeout=220)
load=json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
assert load['boot_id']==boot and load['status']=='PASS'
audit=run('python3','/home/debian/verify_safe_memory.py','--files-only',timeout=140)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
samples=[]
for _ in range(30):
    samples.append(dict(cpu_khz=[int(Path('/sys/devices/system/cpu/cpufreq/policy%d/scaling_cur_freq'%i).read_text())
        for i in (0,4)],GPU_runtime=Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip()))
    time.sleep(.4)
assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
assert not run('systemctl','--failed','--no-legend','--plain').strip()
installed=json.loads((state/'boot-panel-installed.json').read_text())
run('python3',installed['installer'],'verify',installed['toc0_sha256'])
record=dict(status='PASS',boot_id=boot,PMIC_key_on_qualified=proof,combined_load=load,file_audit=audit,
    idle_samples=samples,CPU_minimum_khz=[min(s['cpu_khz'][i] for s in samples) for i in (0,1)],
    GPU_autosuspend_observed=any(s['GPU_runtime']=='suspended' for s in samples),
    scope='Bounded tests; battery and USB retained. No full battery-disconnection test.',
    first_light_confirmation='pending separate human record')
(state/'boot-panel-final-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
os.sync()
print('EARLY_PANEL_KEY_ON_FULL_STACK_LOAD_AND_FILE_AUDIT_PASS',json.dumps(dict(boot_id=boot,
    seconds=load['seconds'],CPU_minimum_khz=record['CPU_minimum_khz'],
    GPU_autosuspend_observed=record['GPU_autosuspend_observed'])),flush=True)
