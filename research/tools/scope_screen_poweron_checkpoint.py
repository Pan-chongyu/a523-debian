"""Keep the captured files intact and clarify historical versus current power-on qualification."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
base = root/'build/screen-poweron-installed-checkpoint'
source = base.with_suffix('.tar.gz')
record = json.loads(base.with_suffix('.json').read_text())
assert hashlib.sha256(source.read_bytes()).hexdigest() == record['archive_sha256']
contents = {}
with tarfile.open(source, 'r:gz') as archive:
    manifest = json.load(archive.extractfile('MANIFEST.json'))
    for name, digest in manifest['files'].items():
        data = archive.extractfile(name).read()
        assert hashlib.sha256(data).hexdigest() == digest, name
        contents[name] = data
manifest['previous_pmic_poweroff_key_on_tested'] = manifest.pop('poweroff_cold_boot_tested')
manifest['this_screen_revision_poweroff_key_on_tested'] = False
manifest['this_screen_revision_poweroff_key_on_status'] = 'deferred at user request; keep desktop running'
manifest['scope'] = ('actual verified screen power-on sequencing and right-landscape default on normal reboot; '
                     'previously verified unchanged PMIC poweroff handler, codec, trained DRAM/GPU/CPU/cooling; '
                     'current and original kernel boot slots and rollback files; no rootfs or credentials')
manifest['captured_source_archive_sha256'] = record['archive_sha256']
for name, local in [('proof/poweron-qualification.json', 'build/screen-poweron/QUALIFICATION.json'),
                    ('proof/usb-transfer-limitation.json', 'build/screen-poweron/TRANSFER_NOTE.json')]:
    contents[name] = (root/local).read_bytes()
manifest['files'] = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
destination = root/'build/screen-poweron-installed-scoped-checkpoint.tar.gz'
with destination.open('xb') as stream:
    with tarfile.open(fileobj=stream, mode='w:gz', compresslevel=3) as archive:
        for name, data in dict(contents, **{'MANIFEST.json': (json.dumps(manifest, indent=2)+'\n').encode()}).items():
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), 0o600
            archive.addfile(member, io.BytesIO(data))
with tarfile.open(destination, 'r:gz') as archive:
    assert set(archive.getnames()) == set(contents) | {'MANIFEST.json'}
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, name
result = dict(manifest, archive_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
              archive_bytes=destination.stat().st_size, every_member_verified=True)
destination.with_suffix('').with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
print('SCREEN_POWERON_SCOPED_CHECKPOINT_EVERY_MEMBER_VERIFIED', json.dumps({
    'files': len(contents), 'bytes': result['archive_bytes'], 'sha256': result['archive_sha256']}))
