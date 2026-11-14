"""Repackage the frozen double-buffer build with the concurrent settings fix."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
folder = root/'build/screen-doublebuffer-r2'
before = json.loads((folder/'screen-runtime-doublebuffer-FILES.json').read_text())
assert before['files']['usr/local/bin/tzx-screen']['sha256'] == '2ececea6e21c539daaa5d4be5e29f387510c94085a6ef4f7edbe2906b956c35f'
package = folder/'screen-runtime-doublebuffer.tar.gz'
assert hashlib.sha256(package.read_bytes()).hexdigest() == before['package_sha256']
with tarfile.open(package, 'r:gz') as archive:
    assert set(archive.getnames()) == set(before['files'])
    files = {name: archive.extractfile(name).read() for name in archive.getnames()}
for name, data in files.items():
    assert hashlib.sha256(data).hexdigest() == before['files'][name]['sha256'], name
files['usr/local/bin/tzx-screen'] = (root/'firmware/tzx_screen.py').read_bytes()
record = dict(before, settings_save_revision=2, files={})
destination = folder/'screen-runtime-doublebuffer-settings.tar.gz'
with destination.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
    for name, data in files.items():
        entry = tarfile.TarInfo(name)
        entry.size, entry.mode, entry.mtime = len(data), before['files'][name]['mode'], 0
        archive.addfile(entry, io.BytesIO(data))
        record['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'mode': entry.mode}
record['package_sha256'] = hashlib.sha256(destination.read_bytes()).hexdigest()
with (folder/'screen-runtime-doublebuffer-settings-FILES.json').open('x') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print('TZX_SCREEN_SETTINGS_PACKAGE', json.dumps(record))
