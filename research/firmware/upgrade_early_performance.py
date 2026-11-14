"""Install early qualified CPU/GPU performance and remove application preloading."""
import hashlib,json,os,subprocess,sys
from pathlib import Path

assert os.geteuid()==0 and sys.argv[1:] in (['install'],['verify'],['restore'])
STATE=Path('/var/lib/tzx/performance-mode-installed.json')
ROOT=Path('/usr/local/lib/tzx-performance-mode')
BACKUP=Path('/root/tzx-recovery/performance-mode-v1/revision3-before')
sha=lambda data:hashlib.sha256(data).hexdigest()
run=lambda *cmd:subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT,timeout=60)
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
baseline_units=('tzx-cpufreq','tzx-cpu-cooling','tzx-cpu-performance')

def atomic(path,data,mode=0o644):
    path=Path(path);assert not path.is_symlink()
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.performance-new')
    with temporary.open('wb') as stream:
        stream.write(data);os.fchmod(stream.fileno(),mode);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)

def restore_revision():
    before=json.loads((BACKUP/'before.json').read_text())
    run('systemctl','stop','tzx-cpu-performance-mode')
    # Reboot will load the original owner; do not unload live hardware drivers.
    for name,item in reversed(list(before['files'].items())):
        path=Path(name)
        if item is None:path.unlink(missing_ok=True)
        else:
            data=(BACKUP/'files'/name.lstrip('/')).read_bytes()
            assert sha(data)==item['sha256'];atomic(path,data,item['mode'])
    for name,enabled in before['baseline_unit_enabled'].items():
        run('systemctl','enable' if enabled=='enabled' else 'disable',name)
    atomic(STATE,(BACKUP/'installed-before.json').read_bytes(),0o600)
    run('systemctl','daemon-reload')

if sys.argv[1]=='install':
    installed=json.loads(STATE.read_text())
    assert installed['state']=='installed' and 'revision' not in installed
    if BACKUP.exists():
        assert (BACKUP/'installed-before.json').read_bytes()==STATE.read_bytes()
        previous=json.loads((BACKUP/'before.json').read_text())
        for name,item in previous['files'].items():
            assert (sha(Path(name).read_bytes())==item['sha256'] if item else not Path(name).exists()),name
    for name,item in installed['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    assert run('systemctl','is-active','tzx-cpu-dvfs','tzx-gpu-performance').split()==['active','active']
    payload={
        str(ROOT/'mode.py'):Path('/home/debian/tzx_performance_mode.py').read_bytes(),
        str(ROOT/'early-check.py'):Path('/home/debian/tzx_early_performance_check.py').read_bytes(),
        '/etc/systemd/system/tzx-cpu-performance-mode.service':Path('/home/debian/tzx-cpu-performance-mode.service').read_bytes(),
        '/etc/systemd/system/tzx-early-performance-check.service':Path('/home/debian/tzx-early-performance-check.service').read_bytes(),
        '/etc/systemd/system/tzx-cpu-dvfs.service':Path('/home/debian/tzx-early-cpu-performance.conf').read_bytes(),
        '/usr/local/lib/tzx-cpu-full/runtime.py':Path('/home/debian/tzx_cpu_early_performance_runtime.py').read_bytes(),
        '/usr/local/lib/tzx-gpu-devfreq/runtime.py':Path('/home/debian/tzx_gpu_max_performance_runtime.py').read_bytes(),
        '/usr/local/lib/tzx-gpu-devfreq/startup.py':Path('/home/debian/tzx_gpu_max_performance_startup.py').read_bytes()}
    for component in ('cpu-full','gpu-devfreq'):
        name='/usr/local/lib/tzx-'+component+'/manifest.json'
        manifest=json.loads(Path(name).read_text())
        for target,digest in manifest['files'].items():assert sha(Path(target).read_bytes())==digest,target
        for target,data in payload.items():
            if target in manifest['files']:manifest['files'][target]=sha(data)
        payload[name]=(json.dumps(manifest,indent=2)+'\n').encode()
    manifest=dict(profile='qualified-early-CPU-GPU-max-performance-no-preload',
        files={name:sha(data) for name,data in payload.items()})
    payload[str(ROOT/'manifest.json')]=(json.dumps(manifest,indent=2)+'\n').encode()
    removed=(str(ROOT/'cache.py'),'/etc/systemd/system/tzx-app-cache.service')
    BACKUP.mkdir(mode=0o700,exist_ok=True)
    atomic(BACKUP/'installed-before.json',STATE.read_bytes(),0o600)
    before=dict(files={},baseline_unit_enabled={name:subprocess.run(['systemctl','is-enabled',name],text=True,capture_output=True).stdout.strip() for name in baseline_units})
    for name in (*payload,*removed):
        path=Path(name)
        if path.exists():
            data=path.read_bytes();mode=path.stat().st_mode&0o777
            atomic(BACKUP/'files'/name.lstrip('/'),data,mode)
            before['files'][name]=dict(sha256=sha(data),mode=mode)
        else:before['files'][name]=None
    atomic(BACKUP/'before.json',(json.dumps(before,indent=2)+'\n').encode(),0o600)
    try:
        print(run('systemctl','disable','--now','tzx-app-cache'),end='')
        # The replacement owns CPU policies from the start; avoid old automatic
        # units racing or waiting for the graphical health checks it precedes.
        print(run('systemctl','disable',*baseline_units),end='')
        run('systemctl','stop','tzx-cpu-performance-mode')
        for name,data in payload.items():
            if name.endswith('.py'):compile(data,name,'exec')
            atomic(name,data)
        for name in removed:Path(name).unlink()
        run('systemctl','daemon-reload')
        print(run('systemd-analyze','verify','--man=no',*[str(Path('/etc/systemd/system')/name) for name in ('tzx-cpu-dvfs.service','tzx-gpu.service','lightdm.service','tzx-cpu-performance-mode.service')]),end='')
        record=dict(state='installed',revision=3,profile=manifest['profile'],
            installed_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            files={name:dict(installed_sha256=sha(data),mode=0o644) for name,data in payload.items()},
            removed_files=list(removed),backup=str(BACKUP),browser_preload=False,
            CPU_kernel_modules_and_thermal_thresholds_unchanged=True,GPU_native_clock_and_thermal_owner_unchanged=True)
        atomic(STATE,(json.dumps(record,indent=2)+'\n').encode(),0o600)
        print(run('systemctl','start','tzx-cpu-performance-mode'),end='')
        os.sync()
    except BaseException as error:
        if isinstance(error,subprocess.CalledProcessError):print(error.output,flush=True)
        restore_revision();raise
    print('EARLY_CPU_GPU_PERFORMANCE_AND_NO_PRELOAD_INSTALLED',flush=True)
elif sys.argv[1]=='verify':
    record=json.loads(STATE.read_text());assert record['state']=='installed' and record['revision']==3
    for name,item in record['files'].items():
        path=Path(name)
        assert sha(path.read_bytes())==item['installed_sha256'],name
        assert path.stat().st_uid==0 and path.stat().st_mode&0o777==item['mode'],name
    assert all(not Path(name).exists() for name in record['removed_files'])
    assert not Path('/etc/systemd/system/graphical.target.wants/tzx-app-cache.service').exists()
    assert run('systemctl','is-active','tzx-cpu-performance-mode').strip()=='active'
    assert all(Path('/sys/devices/system/cpu/cpufreq/policy'+str(n)+'/scaling_governor').read_text().strip()=='performance' for n in (0,4))
    print('EARLY_CPU_GPU_FILES_AND_NO_PRELOAD_VERIFIED',flush=True)
else:
    record=json.loads(STATE.read_text());assert record['revision']==3
    for name,item in record['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    restore_revision()
    print(run('python3','/home/debian/install_performance_mode.py','restore'),end='')
    print('ORIGINAL_CPU_GPU_AUTOMATIC_POLICIES_RESTORED_REBOOT_TO_APPLY_EARLY_OWNER',flush=True)
