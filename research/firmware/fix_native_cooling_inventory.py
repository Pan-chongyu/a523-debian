"""Allow the independently owned Panfrost cooling device during CPU fallback."""
import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
target=Path('/usr/local/lib/tzx-cpu-cooling/runtime.py')
source=Path('/home/debian/tzx_cpu_cooling_runtime.py').read_bytes()
old=target.read_bytes()
assert hashlib.sha256(old).hexdigest()=='804da501da2533ecbe57abcde18681ee180ddb5b523280199627200c0cae779a'
compile(source,str(target),'exec')
backup=Path('/root/tzx-recovery/native-cooling-inventory')
assert not backup.exists()
backup.mkdir(parents=True)
(backup/'runtime.py').write_bytes(old)
state_path=Path('/var/lib/tzx/cpu-cooling-installed.json')
(backup/'state-before.json').write_bytes(state_path.read_bytes())
temporary=target.with_suffix('.native-new')
with temporary.open('wb') as stream:
    stream.write(source);os.fchmod(stream.fileno(),0o644);stream.flush();os.fsync(stream.fileno())
temporary.replace(target)
state=json.loads(state_path.read_text())
state['files']['usr/local/lib/tzx-cpu-cooling/runtime.py']=hashlib.sha256(source).hexdigest()
state['native_gpu_cooling_inventory_compatibility']=True
state_path.write_text(json.dumps(state,indent=2)+'\n')
subprocess.run(['systemctl','stop','tzx-cpu-cooling'],check=True,timeout=30)
# A previously failed oneshot may have loaded its module without reaching
# the active state, in which case systemd does not invoke ExecStop.
subprocess.run(['python3',str(target),'stop'],check=True,timeout=30)
subprocess.run(['systemctl','reset-failed','tzx-cpu-cooling'],check=True)
subprocess.run(['systemctl','start','tzx-cpu-cooling'],check=True,timeout=60)
subprocess.run(['python3',str(target),'verify'],check=True,timeout=30)
os.sync()
print('BASELINE_CPU_THERMAL_FALLBACK_WITH_NATIVE_GPU_COOLER_PASS',flush=True)
