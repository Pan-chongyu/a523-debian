"""Validate trained RAM before the early CPU owner and graphical startup."""
import hashlib,json,os,subprocess,time
from pathlib import Path
assert os.geteuid()==0
started=time.monotonic()
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
result=subprocess.check_output(['python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'],text=True,timeout=25)
assert 'TZX_DRAM_GPU_HARDWARE_GUARD_PASS' in result
for name in ('cpu-full','gpu-devfreq'):
    proof=json.loads(Path('/var/lib/tzx',name+'-qualified.json').read_text())
    assert proof['trial']['status']=='PASS' and proof['trial']['baseline_restored']
manifest=json.loads(Path('/usr/local/lib/tzx-cpu-full/manifest.json').read_text())
for name,digest in manifest['files'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
memory=subprocess.check_output(['/home/debian/memory-check-bounded','256'],text=True,timeout=20)
assert 'MEMORY_TEST_256_MIB_8_THREADS_PASS' in memory
record=dict(status='PASS',boot_id=boot,seconds=round(time.monotonic()-started,3),
    memory_result=memory,qualified_full_4GiB_and_voltage_guard=True,before_gpu_and_lightdm=True)
Path('/run/tzx-early-performance-check.json').write_text(json.dumps(record,indent=2)+'\n')
print('EARLY_PERFORMANCE_TRAINED_RAM_AND_HARDWARE_PASS',json.dumps(record),flush=True)
