"""Recheck GPU after the recorded CPU service-transition watchdog reset."""
import hashlib
import json
from pathlib import Path
import subprocess

def run(*command,timeout=60):
    return subprocess.check_output(command,text=True,stderr=subprocess.STDOUT,timeout=timeout)
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
root=Path('/usr/local/lib/tzx-gpu-performance')
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
failure=json.loads(Path('/var/lib/tzx/gpu-performance-failure.json').read_text())
assert failure['boot_id']==boot and 'Unclean previous performance boot' in failure['error']
previous=run('journalctl','-b','-1','-u','tzx-cpu-dvfs-trial','-o','cat','--no-pager')
assert "TimeoutExpired(('systemctl', 'stop', 'tzx-cpufreq.service'), 45)" in previous
assert json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())['boot_id']==boot
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
for path,digest in json.loads((root/'manifest.json').read_text())['files'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard')
print(run('python3','/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py','--node','/dev/dri/by-path/platform-tzx-de-scanout-card'))
revoked=Path('/var/lib/tzx/gpu-performance-revoked.json')
record=json.loads(revoked.read_text())
assert record['trial']['status']==record['controls']['status']=='PASS'
record['control_watchdog_requalification']={'boot_id':boot,'cause':'CPU baseline cooler startup raced with trial governor change; no DVFS module loaded in that attempt','pixel_render':'PASS'}
qualified=Path('/var/lib/tzx/gpu-performance-qualified.json')
assert not qualified.exists()
qualified.write_text(json.dumps(record,indent=2)+'\n')
run('systemctl','reset-failed','tzx-gpu-performance.service')
run('systemctl','start','tzx-gpu-performance.service')
text=run('runuser','-u','debian','--','env','DISPLAY=:0','XAUTHORITY=/home/debian/.Xauthority',
         'glmark2-es2','--off-screen','--size','640x480','-b',':duration=1',timeout=90)
assert 'Mali-G57 (Panfrost)' in text and 'glmark2 Score:' in text and 'Error:' not in text
Path('/home/debian/gpu-performance/after-cpu-control-watchdog.log').write_text(text)
assert json.loads(Path('/run/tzx-gpu-performance.json').read_text())['actual_mhz']==600
print('GPU_600_MHZ_REQUALIFIED_AFTER_CPU_CONTROL_WATCHDOG')
