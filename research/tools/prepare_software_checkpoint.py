"""Prepare an explicit, credential-free request for an installed-runtime snapshot."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = set()
for name in ('runtime-peripherals/FILES.json',
             'peripheral-kernel/graphics-runtime.json',
             'peripheral-kernel/bluetooth-runtime.json',
             'audio-codec/audio-runtime.json',
             'acceleration-kernel/acceleration-runtime.json',
             'acceleration-hardware/acceleration-hardware.json',
             'tablet-keys/tablet-keys.json'):
    record = json.loads((root/'build'/name).read_text())
    paths.update(record.get('files', record))
paths.update(('etc/systemd/system/tzx-gpu.service.d/90-unqualified.conf',
              'etc/X11/xorg.conf.d/20-tzx-display.conf'))
assert all(p.startswith(('boot/config-', 'etc/', 'lib/', 'usr/local/', 'usr/share/drirc.d/',
                         'usr/lib/systemd/system-generators/tzx-'))
           and '..' not in Path(p).parts and not Path(p).is_absolute() for p in paths)
request = {'paths': sorted(paths), 'bundle': json.loads(
    (root/'build/gpu-clockfix-kernel/linux-bundle.json').read_text())}
(root/'build/software-checkpoint-request.json').write_text(json.dumps(request, indent=2)+'\n')
print('CHECKPOINT_REQUEST', len(paths), 'explicit files, no user credentials')
