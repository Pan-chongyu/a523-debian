"""Confirm a native GPU safety ceiling overrides the user's high minimum."""
import json,os,signal,subprocess,time
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
gpu=Path('/sys/class/devfreq/1800000.gpu')
params=Path('/sys/module/tzx_gpu_devfreq_guard/parameters')
assert (gpu/'min_freq').read_text().strip()=='600000000'
assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip()=='on'
pid=int(subprocess.check_output(['systemctl','show','tzx-gpu-performance','-p','MainPID','--value'],text=True))
assert pid>1 and int((params/'fault').read_text())==0
record=dict(boot_id=boot,requested_gpu_minimum_hz=600000000)
try:
    os.kill(pid,signal.SIGSTOP)
    (params/'maximum_mhz').write_text('200')
    for attempt in range(50):
        frequency=int((gpu/'cur_freq').read_text());limit=int((params/'limit_mhz').read_text())
        if frequency<=200000000 and limit==200:break
        time.sleep(.02)
    else:raise RuntimeError(('GPU maximum ceiling failed to override minimum',frequency,limit))
    record.update(test_safety_ceiling_mhz=limit,actual_gpu_hz=frequency,high_minimum_does_not_bypass_native_maximum=True)
finally:
    (params/'maximum_mhz').write_text('600')
    os.kill(pid,signal.SIGCONT)
assert int((params/'fault').read_text())==0
record['status']='PASS'
Path('/var/lib/tzx/performance-mode-caps-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
print('GPU_NATIVE_SAFETY_CAP_OVERRIDES_HIGH_PERFORMANCE_FLOOR_PASS',json.dumps(record),flush=True)
