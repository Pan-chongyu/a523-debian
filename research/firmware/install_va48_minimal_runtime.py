"""Install verified isolated runtime files; generator does nothing on old #5."""
import hashlib,json,os,subprocess,tarfile
from pathlib import Path,PurePosixPath
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
archive=Path('/home/debian/va48-kernel/minimal-runtime.tar.gz')
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='78a0a488b140bd3ec5141f761acfa05e64b83c86b39b6512ed90ddfe6653b742'
with tarfile.open(archive,'r:gz') as stream:
    members=stream.getmembers()
    assert all(m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts for m in members)
    manifest=json.load(stream.extractfile('FILES.json'))
    assert len(manifest)==43 and len(members)==44
    assert set(m.name for m in members)==set(manifest)|{'FILES.json'}
    content={name:stream.extractfile(name).read() for name in manifest}
    for name,data in content.items():
        assert name.startswith(('lib/modules/7.3.3-tzx-a523-va48/', 'usr/local/lib/tzx-va48/rtc/')) or name in (
            'boot/config-7.3.3-tzx-a523-va48','usr/lib/systemd/system-generators/tzx-va48-diagnostic')
        assert hashlib.sha256(data).hexdigest()==manifest[name]
        target=Path('/')/name
        assert not target.is_symlink()
        if target.exists():assert target.read_bytes()==data,name
    for name,data in content.items():
        target=Path('/')/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            with target.open('xb') as output:
                output.write(data);output.flush();os.fsync(output.fileno())
        target.chmod(0o755 if 'system-generators/' in name else 0o644)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==manifest[name]
    record=Path('/home/debian/va48-kernel/installed-runtime-files.json')
    record.write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run(['depmod','7.3.3-tzx-a523-va48'],check=True,timeout=25)
subprocess.run(['systemctl','daemon-reload'],check=True,timeout=30)
os.sync()
print('VA48_ISOLATED_RUNTIME_INSTALLED_VERIFIED',len(manifest),flush=True)
