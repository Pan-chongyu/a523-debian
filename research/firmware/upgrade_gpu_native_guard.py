"""Qualify thermal throttling, emergency cleanup and lease expiry independently."""
import hashlib,json,os,subprocess,tarfile,time
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
sha=lambda b:hashlib.sha256(b).hexdigest()
pin='8c5d547f5ab0a9aa24428dacbc9a236c8fb23c589726c24e618b6dd5e5e8376c'
archive=Path('/home/debian/cpu-gpu-runtime.tar.gz')
assert sha(archive.read_bytes())==pin
root=Path('/usr/local/lib/tzx-gpu-devfreq')
df=Path('/sys/class/devfreq/1800000.gpu')
param=Path('/sys/module/tzx_gpu_devfreq_guard/parameters')
state_path=Path('/var/lib/tzx/cpu-gpu-native-installed.json')
state=json.loads(state_path.read_text())
assert state['package_sha256']=='d8c7d84711834086a1bdd70288af3481eeba79cfa9c8b0bfebae5833d6c40c5f'
proof=json.loads(Path('/var/lib/tzx/gpu-devfreq-revoked.json').read_text())
assert proof['trial']['status']=='PASS' and proof['trial']['baseline_restored']
backup=Path('/root/tzx-recovery/gpu-native-guard-v2')
assert not backup.exists()
backup.mkdir(parents=True)
(backup/'state-before.json').write_bytes(state_path.read_bytes())
with tarfile.open(archive) as package:
    contents={'/'+m.name:package.extractfile(m).read() for m in package.getmembers()}
assert len(contents)==16
changed={name:data for name,data in contents.items() if Path(name).read_bytes()!=data}
assert set(changed)=={str(root/name) for name in ('runtime.py','tzx_gpu_devfreq_guard.ko','manifest.json')}
for name,data in changed.items():
    (backup/Path(name).name).write_bytes(Path(name).read_bytes())
    if name.endswith('.py'):compile(data,name,'exec')

def run(*args,timeout=60):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)

def unload():
    (df/'min_freq').write_text('150000000')
    (df/'max_freq').write_text('200000000')
    if param.exists():run('rmmod','tzx_gpu_devfreq_guard')

def load(*args):
    run('insmod',str(root/'tzx_gpu_devfreq_guard.ko'),*args)
    assert int((param/'fault').read_text())==0

run('systemctl','stop','tzx-gpu-performance')
unload()
for name,data in changed.items():
    target=Path(name);tmp=target.with_suffix(target.suffix+'.guard-new')
    with tmp.open('wb') as stream:
        stream.write(data);os.fchmod(stream.fileno(),0o644);stream.flush();os.fsync(stream.fileno())
    tmp.replace(target)
records={};children=[]
try:
    load('first_trip=30000','lease_seconds=3')
    (df/'max_freq').write_text('600000000')
    (param/'maximum_mhz').write_text('600')
    assert int((param/'limit_mhz').read_text())==400
    records['thermal_first_limit_mhz']=400
    try:(param/'maximum_mhz').write_text('800')
    except OSError:records['unqualified_800_rejected']=True
    else:raise AssertionError('800 MHz accepted')
    time.sleep(3.5)
    assert int((param/'limit_mhz').read_text())==200
    records['expired_lease_limit_mhz']=200
    unload();load('first_trip=30000','second_trip=35000')
    (df/'max_freq').write_text('600000000');(param/'maximum_mhz').write_text('600')
    assert int((param/'limit_mhz').read_text())==200
    records['thermal_second_limit_mhz']=200
    unload()
    temperatures=[int(p.read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')]
    threshold=max(temperatures)+3000
    assert 30000<threshold<65000
    load('fault_trip='+str(threshold))
    (param/'maximum_mhz').write_text('600')
    code='import time\nend=time.monotonic()+20\nx=1\nwhile time.monotonic()<end:x=(x*1664525+1013904223)&0xffffffff\n'
    children=[subprocess.Popen(['taskset','-c',str(n),'python3','-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) for n in range(8)]
    until=time.monotonic()+18
    while time.monotonic()<until and int((param/'fault').read_text())==0:time.sleep(.1)
    assert int((param/'fault').read_text())==-75
    assert int((param/'fault_temperature_mc').read_text())>=threshold
    assert int((param/'limit_mhz').read_text())==200
    try:(param/'maximum_mhz').write_text('600')
    except OSError:pass
    else:raise AssertionError('Emergency latch allowed a raised ceiling')
    # This used to throw EOVERFLOW and prevent pending-marker cleanup.
    (param/'maximum_mhz').write_text('200')
    records['emergency_latch']=dict(test_threshold_mc=threshold,
        actual_temperature_mc=int((param/'fault_temperature_mc').read_text()),
        cap_mhz=200,raised_ceiling_rejected=True,cleanup_cap_acknowledged=True,
        emulated_temperature=False)
finally:
    for process in children:
        if process.poll() is None:process.terminate()
        process.wait(timeout=5)
    unload();load()
    (df/'max_freq').write_text('200000000')
    (param/'maximum_mhz').write_text('200')
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
records.update(status='PASS',boot_id=boot,production_trips_mc=[65000,70000],
    production_emergency_trip_mc=85000,production_parameters_restored=True,
    guard_sha256=sha((root/'tzx_gpu_devfreq_guard.ko').read_bytes()))
Path('/var/lib/tzx/gpu-native-guard-v2-controls.json').write_text(json.dumps(records,indent=2)+'\n')
proof.update(guard_revision=2,guard_controls=records,scope='Native OPPs qualified; thermal guard v2 requalified; normal reboot pending')
Path('/var/lib/tzx/gpu-devfreq-qualified.json').write_text(json.dumps(proof,indent=2)+'\n')
Path('/var/lib/tzx/gpu-devfreq-pending.json').unlink(missing_ok=True)
state.update(package_sha256=pin,previous_package_sha256=state['package_sha256'],guard_revision=2,
    guard_controls=records,state='guard-v2-online-qualified')
state_path.write_text(json.dumps(state,indent=2)+'\n')
run('systemctl','reset-failed','tzx-gpu-performance')
run('systemctl','start','tzx-gpu-performance')
for unused in range(40):
    status=json.loads(Path('/run/tzx-gpu-performance.json').read_text())
    if status['state']=='active':break
    time.sleep(.5)
assert status['state']=='active'
os.sync()
print('NATIVE_GPU_GUARD_V2_ALL_CONTROLS_PASS',json.dumps(records),flush=True)
