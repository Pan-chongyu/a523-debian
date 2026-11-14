"""Replace temporary boosts with the user's requested persistent performance mode."""
import hashlib,json,os,subprocess
from pathlib import Path
import sys
assert os.geteuid()==0 and sys.argv[1:] in (['install'],['verify'],['restore'])
ROOT=Path('/usr/local/lib/tzx-performance-mode')
STATE=Path('/var/lib/tzx/performance-mode-installed.json')
BACKUP=Path('/root/tzx-recovery/performance-mode-v1')
sha=lambda b:hashlib.sha256(b).hexdigest()
def run(*cmd,timeout=45):return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT,timeout=timeout)
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
if sys.argv[1]=='install':
    assert not ROOT.exists() and not STATE.exists() and not BACKUP.exists()
    BACKUP.mkdir(mode=0o700)
    # Preserve the superseded overlay before removing its launcher overrides.
    old=Path('/var/lib/tzx/app-launch-installed.json')
    previous=json.loads(old.read_text());assert previous['state']=='installed'
    withdrawn=BACKUP/'withdrawn-short-boost';withdrawn.mkdir()
    (withdrawn/'installed.json').write_bytes(old.read_bytes())
    for index,(name,item) in enumerate(previous['files'].items()):
        data=Path(name).read_bytes();assert sha(data)==item['installed_sha256']
        (withdrawn/('file-'+str(index))).write_bytes(data)
    print(run('python3','/home/debian/install_app_launch.py','restore'),end='')
    cache_unit=Path('/home/debian/tzx-app-cache.service').read_text().replace('/usr/local/lib/tzx-app-launch/cache.py',str(ROOT/'cache.py'))
    assert str(ROOT/'cache.py') in cache_unit
    payload={ROOT/'mode.py':Path('/home/debian/tzx_performance_mode.py').read_bytes(),
        ROOT/'cache.py':Path('/home/debian/tzx_app_cache.py').read_bytes(),
        Path('/etc/systemd/system/tzx-cpu-performance-mode.service'):Path('/home/debian/tzx-cpu-performance-mode.service').read_bytes(),
        Path('/etc/systemd/system/tzx-app-cache.service'):cache_unit.encode()}
    record=dict(state='installing',profile='user-persistent-performance-with-app-preload',
        installed_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),files={})
    for index,(path,data) in enumerate(payload.items()):
        assert not path.exists(),path
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o644)
        record['files'][str(path)]={'installed_sha256':sha(data),'before':None,'mode':0o644}
    manifest={'profile':record['profile'],'files':{name:item['installed_sha256'] for name,item in record['files'].items()}}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    record['files'][str(ROOT/'manifest.json')]={'installed_sha256':sha((ROOT/'manifest.json').read_bytes()),'before':None,'mode':0o644}
    STATE.write_text(json.dumps(record,indent=2)+'\n')
    run('systemctl','daemon-reload')
    print(run('systemd-analyze','verify','/etc/systemd/system/tzx-cpu-performance-mode.service','/etc/systemd/system/tzx-app-cache.service'),end='')
    print(run('systemctl','enable','--now','tzx-cpu-performance-mode','tzx-app-cache',timeout=40),end='')
    record['state']='installed';STATE.write_text(json.dumps(record,indent=2)+'\n');os.sync()
    print('PERSISTENT_CPU_PERFORMANCE_MODE_INSTALLED',flush=True)
elif sys.argv[1]=='verify':
    record=json.loads(STATE.read_text());assert record['state']=='installed'
    for name,item in record['files'].items():
        assert sha(Path(name).read_bytes())==item['installed_sha256'],name
        assert Path(name).stat().st_uid==0 and Path(name).stat().st_mode&0o777==item['mode'],name
    assert run('systemctl','is-active','tzx-cpu-performance-mode').strip()=='active'
    assert run('systemctl','is-enabled','tzx-cpu-performance-mode','tzx-app-cache').split()==['enabled','enabled']
    assert all(Path('/sys/devices/system/cpu/cpufreq/policy'+str(n)+'/scaling_governor').read_text().strip()=='performance' for n in (0,4))
    assert not Path('/etc/systemd/system/graphical.target.wants/tzx-app-boost.service').exists()
    print('PERSISTENT_CPU_PERFORMANCE_MODE_FILES_GOVERNORS_AUTOSTART_PASS',flush=True)
else:
    record=json.loads(STATE.read_text());assert record['state']=='installed'
    for name,item in record['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    print(run('systemctl','disable','--now','tzx-cpu-performance-mode','tzx-app-cache'),end='')
    for name in reversed(record['files']):Path(name).unlink()
    ROOT.rmdir();run('systemctl','daemon-reload')
    record['state']='restored';STATE.write_text(json.dumps(record,indent=2)+'\n');os.sync()
    print('PERSISTENT_MODE_REMOVED_AUTOMATIC_CPU_GOVERNOR_RESTORED',flush=True)
