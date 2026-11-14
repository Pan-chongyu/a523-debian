"""Install qualified native GPU and bin-gated CPU services, with a saved rollback."""
import hashlib,json,os,subprocess,sys,tarfile,time
from pathlib import Path,PurePosixPath

assert os.geteuid()==0 and len(sys.argv)==3 and sys.argv[1] in ('install','restore')
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
operation,pin=sys.argv[1:]
stage=Path('/home/debian')
archive_path=stage/'cpu-gpu-runtime.tar.gz'
backup=Path('/root/tzx-recovery/cpu-gpu-native-runtime')
state_path=Path('/var/lib/tzx/cpu-gpu-native-installed.json')
BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
sha=lambda b:hashlib.sha256(b).hexdigest()


def run(*args,timeout=100):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)


def atomic(path,data,mode=0o644):
    assert not path.is_symlink();path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.native-new')
    with temp.open('wb') as f:
        f.write(data);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
    temp.replace(path)


def record(path,value):atomic(path,(json.dumps(value,indent=2)+'\n').encode(),0o600)


def settle(unit,path):
    for attempt in range(100):
        if path.exists() and json.loads(path.read_text()).get('state')=='active':return json.loads(path.read_text())
        assert subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0,run('journalctl','-u',unit,'--no-pager','-n','30')
        time.sleep(.5)
    raise RuntimeError(unit+' did not become active')


def unload_gpu_native():
    if Path('/sys/class/devfreq/1800000.gpu').exists():
        run('python3','/usr/local/lib/tzx-gpu-devfreq/cleanup.py')
    if Path('/sys/module/tzx_gpu_devfreq_guard').exists():run('rmmod','tzx_gpu_devfreq_guard')
    if Path('/sys/module/panfrost').exists():run('rmmod','panfrost',timeout=20)
    if Path('/sys/module/tzx_gpu_devfreq_opps').exists():run('rmmod','tzx_gpu_devfreq_opps')


if operation=='restore':
    state=json.loads(state_path.read_text());assert state['package_sha256']==pin
    run('systemctl','stop','tzx-emmc-hs','tzx-cpu-dvfs','tzx-gpu-performance','lightdm')
    unload_gpu_native()
    for name in state['created_files']:
        p=Path(name);assert p.is_file() and not p.is_symlink();p.unlink()
    for name in ('cpu-full-qualified.json','gpu-devfreq-qualified.json'):
        Path('/var/lib/tzx',name).unlink(missing_ok=True)
    run('systemctl','daemon-reload')
    run('insmod','/usr/local/lib/tzx-dram-gpu/panfrost.ko','tzx_dma32=1')
    run('systemctl','start','lightdm','tzx-gpu-performance')
    run('systemctl','start','tzx-cpu-dvfs')
    state['state']='prior-CPU-GPU-runtime-restored';record(state_path,state)
    print('PRIOR_1416_1488_CPU_AND_FIXED_PARENT_GPU_RESTORED',flush=True)
    raise SystemExit(0)

assert sha(archive_path.read_bytes())==pin
assert not backup.exists() and not state_path.exists()
gpu_trial=json.loads((stage/'gpu-devfreq/trial-result.json').read_text())
cpu_trial=json.loads((stage/'cpu-full/trial-result.json').read_text())
assert gpu_trial['status']==cpu_trial['status']=='PASS'
assert gpu_trial['baseline_restored'] and cpu_trial['baseline_restored']
assert gpu_trial['boot_id']==cpu_trial['boot_id']==BOOT
assert cpu_trial['speed_bin']=='vf0300' and cpu_trial['capacity']==[725]*4+[1024]*4
assert cpu_trial['eight_core_checksums']==40 and cpu_trial['clock_transitions']==160
assert cpu_trial['thermal_qos_240MHz']==cpu_trial['lease_expiry_480MHz_900mV']=='PASS'
assert cpu_trial['gpu_score']>400
assert [v['label'] for v in gpu_trial['records'] if v['check']=='GPU scenes']==['150','200','300','400','600','automatic']
with tarfile.open(archive_path) as archive:
    members=archive.getmembers()
    assert len(members)==16 and len({m.name for m in members})==16
    contents={}
    for member in members:
        p=PurePosixPath(member.name)
        assert member.isfile() and not p.is_absolute() and '..' not in p.parts
        assert str(p).startswith(('usr/local/lib/tzx-cpu-full/','usr/local/lib/tzx-gpu-devfreq/','etc/systemd/system/tzx-'))
        target=Path('/')/str(p);assert not target.exists() and not target.is_symlink(),str(target)
        contents[str(target)]=archive.extractfile(member).read()
for component in ('tzx-cpu-full','tzx-gpu-devfreq'):
    manifest=json.loads(contents['/usr/local/lib/'+component+'/manifest.json'])
    assert sha(Path('/boot/Image').read_bytes())==manifest['kernel_image_sha256']
    for name,digest in manifest['files'].items():assert sha(contents[name])==digest,name
cpu_manifest=json.loads(contents['/usr/local/lib/tzx-cpu-full/manifest.json'])
gpu_manifest=json.loads(contents['/usr/local/lib/tzx-gpu-devfreq/manifest.json'])
backup.mkdir(parents=True)
for name in ('cpu-dvfs-qualified.json','gpu-performance-qualified.json'):
    p=Path('/var/lib/tzx')/name
    if p.exists():atomic(backup/name,p.read_bytes(),0o600)
run('systemctl','stop','tzx-emmc-hs','tzx-cpu-dvfs','tzx-gpu-performance')
run('systemctl','stop','lightdm')
assert not Path('/sys/module/tzx_cpufreq_dvfs').exists()
assert not Path('/sys/module/tzx_gpu_performance').exists()
run('rmmod','panfrost',timeout=20)
for name,data in contents.items():atomic(Path(name),data)
record(Path('/var/lib/tzx/cpu-full-qualified.json'),dict(profile=cpu_manifest['profile'],trial=cpu_trial,scope='online-qualified; normal reboot pending'))
record(Path('/var/lib/tzx/gpu-devfreq-qualified.json'),dict(profile=gpu_manifest['profile'],trial=gpu_trial,scope='online-qualified; normal reboot pending'))
state=dict(state='files-installed-not-started',installed_boot_id=BOOT,package_sha256=pin,
    created_files=sorted(contents),backup=str(backup),boot_areas_changed=False)
record(state_path,state)
run('systemctl','daemon-reload')
run('python3','/usr/local/lib/tzx-gpu-devfreq/startup.py',timeout=85)
run('systemctl','start','lightdm')
run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','health',timeout=100)
run('systemctl','start','tzx-gpu-performance')
gpu=settle('tzx-gpu-performance',Path('/run/tzx-gpu-performance.json'))
run('systemctl','start','tzx-cpu-dvfs')
cpu=settle('tzx-cpu-dvfs',Path('/run/tzx-cpu-dvfs.json'))
assert cpu['maximum_khz']==[1416000,1800000] and cpu['capacity']==[725]*4+[1024]*4
assert gpu['clock_owner']=='Panfrost devfreq'
assert Path('/sys/class/devfreq/1800000.gpu/governor').read_text().strip()=='simple_ondemand'
state.update(state='installed-online-qualified',cpu=cpu,gpu=gpu);record(state_path,state)
os.sync()
print('NATIVE_GPU_AND_VF0300_CPU_INSTALLED',json.dumps(dict(cpu=cpu,gpu=gpu)),flush=True)
