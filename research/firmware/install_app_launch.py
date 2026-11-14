"""Install and restore the app-only overlay without modifying qualified drivers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

assert os.geteuid()==0 and sys.argv[1:] in (['install'],['verify'],['restore'])
STAGE=Path('/home/debian/app-launch-stage')
ROOT=Path('/usr/local/lib/tzx-app-launch')
STATE=Path('/var/lib/tzx/app-launch-installed.json')
BACKUP=Path('/root/tzx-recovery/app-launch-v1/overlay')
sha=lambda b:hashlib.sha256(b).hexdigest()
def run(*cmd):return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT,timeout=45)
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'

if sys.argv[1]=='install':
    assert not STATE.exists() and not ROOT.exists() and not BACKUP.exists()
    assert Path('/sys/devices/system/cpu/cpufreq/policy0/scaling_driver').read_text().strip()=='tzx-a523-dvfs2'
    manifest=json.loads((STAGE/'manifest.json').read_text())
    assert set(manifest['files'])=={'boost.py','cache.py','tzx-launch','tzx-app-boost.service','tzx-app-cache.service'}
    for name,digest in manifest['files'].items():assert sha((STAGE/name).read_bytes())==digest,name
    for name in ('boost.py','cache.py'):compile((STAGE/name).read_bytes(),name,'exec')
    payload={ROOT/'boost.py':((STAGE/'boost.py').read_bytes(),0o644,0),
        ROOT/'cache.py':((STAGE/'cache.py').read_bytes(),0o644,0),
        Path('/usr/local/bin/tzx-launch'):((STAGE/'tzx-launch').read_bytes(),0o755,0)}
    for name in ('tzx-app-boost.service','tzx-app-cache.service'):
        payload[Path('/etc/systemd/system')/name]=((STAGE/name).read_bytes(),0o644,0)
    original=Path('/usr/share/applications/firefox-esr.desktop').read_text()
    assert 'Exec=/usr/lib/firefox-esr/firefox-esr %u' in original
    override='\n'.join('Exec=/usr/local/bin/tzx-launch '+line[5:] if line.startswith('Exec=') else line for line in original.splitlines())+'\n'
    payload[Path('/home/debian/.local/share/applications/firefox-esr.desktop')]=(override.encode(),0o644,1000)
    helper=b'''[Desktop Entry]
Version=1.0
Type=X-XFCE-Helper
Name=Firefox ESR
Icon=firefox-esr
StartupNotify=false
X-XFCE-Category=WebBrowser
X-XFCE-Binaries=firefox-esr;
X-XFCE-Commands=/usr/local/bin/tzx-launch /usr/bin/firefox-esr;
X-XFCE-CommandsWithParameter=/usr/local/bin/tzx-launch /usr/bin/firefox-esr "%s";
'''
    payload[Path('/home/debian/.local/share/xfce4/helpers/tzx-firefox.desktop')]=(helper,0o644,1000)
    helpers=Path('/home/debian/.config/xfce4/helpers.rc')
    settings=helpers.read_text().splitlines() if helpers.exists() else []
    indices=[i for i,line in enumerate(settings) if line.startswith('WebBrowser=')]
    assert len(indices)<=1
    if indices:settings[indices[0]]='WebBrowser=tzx-firefox'
    else:settings.append('WebBrowser=tzx-firefox')
    payload[helpers]=( ('\n'.join(settings)+'\n').encode(),0o644,1000)
    # Include existing desktop/panel copies that bypass XDG application lookup.
    for base in (Path('/home/debian/Desktop'),Path('/home/debian/桌面'),Path('/home/debian/.config/xfce4/panel')):
        if not base.exists():continue
        for path in base.rglob('*.desktop'):
            if path.is_symlink() or not path.is_file():continue
            text=path.read_text()
            lines=text.splitlines();changed=False
            for i,line in enumerate(lines):
                if line.startswith('Exec=') and line[5:].split(' ',1)[0] in ('firefox','firefox-esr','/usr/bin/firefox','/usr/bin/firefox-esr','/usr/lib/firefox-esr/firefox-esr','x-www-browser'):
                    lines[i]='Exec=/usr/local/bin/tzx-launch '+line[5:];changed=True
            if changed:payload[path]=(('\n'.join(lines)+'\n').encode(),path.stat().st_mode&0o777,1000)
    BACKUP.mkdir(mode=0o700,parents=True)
    record={'profile':'bounded-app-boost-v1','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'files':{},'state':'installing'}
    for index,(path,(data,mode,uid)) in enumerate(payload.items()):
        previous=None
        if path.exists():
            assert path.is_file() and not path.is_symlink(),path
            old=path.read_bytes();info=path.stat();name='before-'+str(index)
            (BACKUP/name).write_bytes(old)
            previous={'backup':name,'sha256':sha(old),'mode':info.st_mode&0o777,'uid':info.st_uid,'gid':info.st_gid}
        record['files'][str(path)]={'installed_sha256':sha(data),'mode':mode,'uid':uid,'before':previous}
    (BACKUP/'before.json').write_text(json.dumps(record,indent=2)+'\n')
    for path,(data,mode,uid) in payload.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        if uid==1000:
            parent=path.parent
            while parent!=Path('/home/debian') and str(parent).startswith('/home/debian/'):
                os.chown(parent,1000,1000);parent=parent.parent
        path.write_bytes(data);path.chmod(mode);os.chown(path,uid,uid)
    runtime_manifest={'profile':record['profile'],'files':{name:item['installed_sha256'] for name,item in record['files'].items() if not name.startswith('/home/debian/')}}
    (ROOT/'manifest.json').write_text(json.dumps(runtime_manifest,indent=2)+'\n')
    record['files'][str(ROOT/'manifest.json')]={'installed_sha256':sha((ROOT/'manifest.json').read_bytes()),'mode':0o644,'uid':0,'before':None}
    STATE.write_text(json.dumps(record,indent=2)+'\n')
    print(run('systemctl','daemon-reload'),end='')
    print(run('systemd-analyze','verify','/etc/systemd/system/tzx-app-boost.service','/etc/systemd/system/tzx-app-cache.service'),end='')
    print(run('systemctl','enable','--now','tzx-app-boost.service','tzx-app-cache.service'),end='')
    record['state']='installed';STATE.write_text(json.dumps(record,indent=2)+'\n')
    os.sync()
    print('BOUNDED_APP_LAUNCH_OVERLAY_INSTALLED',len(record['files']),flush=True)
elif sys.argv[1]=='verify':
    record=json.loads(STATE.read_text());assert record['state']=='installed'
    for name,item in record['files'].items():
        path=Path(name);assert sha(path.read_bytes())==item['installed_sha256'],name
        assert path.stat().st_uid==item['uid'] and path.stat().st_mode&0o777==item['mode'],name
    print(run('systemctl','is-active','tzx-app-boost'),end='')
    print(run('systemctl','is-enabled','tzx-app-boost','tzx-app-cache'),end='')
    print('APP_LAUNCH_OVERLAY_FILES_AND_AUTOSTART_PASS',len(record['files']),flush=True)
else:
    record=json.loads(STATE.read_text());assert record['state']=='installed'
    for name,item in record['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    print(run('systemctl','disable','--now','tzx-app-boost','tzx-app-cache'),end='')
    for name,item in reversed(list(record['files'].items())):
        path=Path(name);before=item['before']
        if before is None:path.unlink()
        else:
            data=(BACKUP/before['backup']).read_bytes();assert sha(data)==before['sha256']
            path.write_bytes(data);path.chmod(before['mode']);os.chown(path,before['uid'],before['gid'])
    if ROOT.exists():ROOT.rmdir()
    record['state']='restored';STATE.write_text(json.dumps(record,indent=2)+'\n')
    run('systemctl','daemon-reload');os.sync()
    print('APP_LAUNCH_OVERLAY_REMOVED_ORIGINAL_LAUNCHERS_RESTORED',flush=True)
