"""Package boot-managed codec/PH6 audio after successful on-device playback."""
import hashlib
import json
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parents[1]
out=root/'build/audio-codec'
stage=out/'persistent-runtime'
release='7.3.3-tzx-a523-periph1'
files={'lib/modules/'+release+'/extra/'+p.name:p.read_bytes() for p in out.glob('*.ko')}
assert len(files)==3
files['etc/sysctl.d/70-tzx-driver-test-recovery.conf']=(root/'firmware/tzx-driver-test-recovery.conf').read_bytes()
files['etc/systemd/system/tzx-audio.service']=(root/'firmware/tzx-audio.service').read_bytes()
for name in ('tzx-audio-runtime','verify_codec_pcm.py','verify_codec_duplex.py'):
    files['usr/local/lib/tzx-audio/'+name]=(root/'firmware'/name).read_bytes()
files['usr/local/lib/tzx-audio/MODULES.sha256']=''.join(
    hashlib.sha256(data).hexdigest()+'  /'+name+'\n'
    for name,data in sorted(files.items()) if name.endswith('.ko')).encode()
manifest={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}
for name,data in files.items():
    path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
(stage/'FILES.json').write_text(json.dumps(manifest,indent=2)+'\n')
installer='''import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-periph1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/tzx_codec_driver').exists(), 'Unbind and unload old codec before replacing'
assert int(Path('/proc/sys/kernel/tainted').read_text()) & 128 == 0
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('lib/modules/7.3.3-tzx-a523-periph1/extra/tzx_','etc/sysctl.d/70-tzx-','usr/local/lib/tzx-audio/','etc/systemd/system/tzx-audio.service'))
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name;target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tzx-new')
    temporary.write_bytes((stage/name).read_bytes());temporary.chmod(0o644);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
subprocess.run(['depmod','-a',os.uname().release],check=True)
subprocess.run(['sysctl','-p','/etc/sysctl.d/70-tzx-driver-test-recovery.conf'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemd-analyze','verify','tzx-audio.service'],check=True)
subprocess.run(['systemctl','enable','tzx-audio.service'],check=True)
os.sync()
print('AUDIO_RUNTIME_INSTALLED_HASH_VERIFIED',len(files))
'''
(stage/'install.py').write_text(installer,newline='\n')
archive=out/'audio-runtime.tar.gz'
with tarfile.open(archive,'w:gz') as package:
    for name in sorted([*files,'FILES.json','install.py']):package.add(stage/name,arcname=name,recursive=False)
(out/'audio-runtime.json').write_text(json.dumps({'files':manifest,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'speaker_ph6_user_confirmed':True,'autostart_reboot_verified':False},indent=2)+'\n')
print('AUDIO_RUNTIME_PACKAGED',len(files),archive.stat().st_size)
