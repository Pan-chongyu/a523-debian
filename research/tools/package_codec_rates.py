"""Package only the qualified codec module and its active hash list."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
module = 'lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_codec_driver.ko'
old = '3ae8027ef29b6e3f919affe45b34fbb9be44ed28a5399d6532e2adc140b50acd'
data = (root/'build/audio-rates/tzx_codec_driver.ko').read_bytes()
new = hashlib.sha256(data).hexdigest()
assert new == '013bcbe659aba5cae4d747c18fdce0c38b81ba782527bccab528f1de8132bf2d'
hashes = (root/'build/acceleration-kernel/runtime/usr/local/lib/tzx-accel-audio/MODULES.sha256').read_bytes()
assert hashes.count(old.encode()) == 1
files = {module: data, 'usr/local/lib/tzx-accel-audio/MODULES.sha256': hashes.replace(old.encode(), new.encode())}
manifest = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
target = root/'build/audio-rates/audio-rates-runtime.tar.gz'
assert not target.exists()
with tarfile.open(target, 'w:gz') as archive:
    for name, value in dict(files, **{'FILES.json': json.dumps(manifest, indent=2).encode()+b'\n'}).items():
        item = tarfile.TarInfo(name)
        item.size, item.mode = len(value), 0o644
        archive.addfile(item, io.BytesIO(value))
with tarfile.open(target, 'r:gz') as archive:
    for name, digest in manifest.items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest
record = {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'files': manifest,
          'only_codec_rate_fields_and_alsa_masks_changed': True}
(target.parent/'PACKAGE.json').write_text(json.dumps(record, indent=2)+'\n')
print('CODEC_RATE_RUNTIME_PACKAGE_VERIFIED', json.dumps(record))
