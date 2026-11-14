"""Stage a guarded candidate installer; do not enable audio on boot before testing."""
from pathlib import Path
import hashlib
import json
import tarfile

root = Path(__file__).resolve().parents[1]
out = root / 'build/audio-codec'
stage = out / 'runtime'
release = '7.3.3-tzx-a523-periph1'
files = {'lib/modules/' + release + '/extra/' + path.name: path.read_bytes()
         for path in out.glob('*.ko')}
assert len(files) == 3
files['etc/sysctl.d/70-tzx-driver-test-recovery.conf'] = (
    root / 'firmware/tzx-driver-test-recovery.conf').read_bytes()
files['usr/local/lib/tzx-audio/verify_codec_pcm.py'] = (
    root / 'firmware/verify_codec_pcm.py').read_bytes()
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
(stage / 'FILES.json').write_text(json.dumps(manifest, indent=2) + '\n')
installer = '''import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
assert os.uname().release=='7.3.3-tzx-a523-periph1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/tzx_codec_driver').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) & 128 == 0, 'Reboot after an oops first'
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('lib/modules/7.3.3-tzx-a523-periph1/extra/tzx_','etc/sysctl.d/70-tzx-','usr/local/lib/tzx-audio/'))
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name;target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tzx-new')
    temporary.write_bytes((stage/name).read_bytes());temporary.chmod(0o644);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
subprocess.run(['depmod','-a',os.uname().release],check=True)
subprocess.run(['sysctl','-p','/etc/sysctl.d/70-tzx-driver-test-recovery.conf'],check=True)
os.sync()
print('CODEC_CANDIDATE_INSTALLED_NOT_AUTOLOADED',len(files))
'''
(stage / 'install.py').write_text(installer, newline='\n')
archive = out / 'codec-candidate.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install.py']):
        package.add(stage / name, arcname=name, recursive=False)
(out / 'candidate.json').write_text(json.dumps({
    'files': manifest, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'hardware_tested': False, 'boot_enabled': False}, indent=2) + '\n')
print('CODEC_CANDIDATE_PACKAGED_NOT_AUTOLOADED', len(files), archive.stat().st_size)
