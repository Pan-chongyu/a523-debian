"""Stage the frozen candidate; installation requires completed on-board evidence."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root / 'build/gpu-dma32-runtime'
stage = out / 'runtime'
stage.mkdir(parents=True, exist_ok=True)
release = '7.3.3-tzx-a523-accel1'
modules = root / 'build/gpu-dma32-mmu-init'
frozen = json.loads((modules / 'MANIFEST.json').read_text())
files = {}
for source, target in [('panfrost-dma32.ko', 'panfrost.ko'),
                       ('tzx_display-dma32.ko', 'tzx_display.ko')]:
    data = (modules / source).read_bytes()
    assert hashlib.sha256(data).hexdigest() == frozen['modules'][source]['sha256']
    files[f'lib/modules/{release}/updates/tzx-dma32/{target}'] = data
prefix = 'usr/local/lib/tzx-gpu-dma32/'
files[prefix + 'MODULES.sha256'] = ''.join(
    hashlib.sha256(data).hexdigest() + '  /' + name + '\n'
    for name, data in sorted(files.items())).encode()
for name in ('tzx-gpu-dma32-runtime', 'tzx-gpu-lightdm', 'tzx-gpu-dma32-boot-check.py',
             'tzx-gpu-dma32-disable.py', 'tzx_direct_io.py'):
    files[prefix + name] = (root / 'firmware' / name).read_bytes()
files[prefix + 'check-display'] = b'''#!/bin/sh
set -eu
test "$(uname -r)" = 7.3.3-tzx-a523-accel1 || exit 0
test "$(cat /sys/class/block/mmcblk0/device/cid)" = 3e01ff55454d20202010209170281b59
sha256sum -c /usr/local/lib/tzx-gpu-dma32/MODULES.sha256
test "$(modinfo -n tzx_display)" = /lib/modules/7.3.3-tzx-a523-accel1/updates/tzx-dma32/tzx_display.ko
'''
files['etc/modprobe.d/tzx-gpu-dma32.conf'] = b'options panfrost tzx_dma32=1\n'
files['etc/systemd/system/tzx-display.service.d/92-dma32.conf'] = b'''[Service]
ExecStartPre=/bin/sh /usr/local/lib/tzx-gpu-dma32/check-display
'''
files['etc/systemd/system/tzx-gpu.service.d/95-dma32.conf'] = b'''[Unit]
OnFailure=tzx-gpu-dma32-fallback.service
[Service]
ExecStart=
ExecStart=/bin/sh /usr/local/lib/tzx-gpu-dma32/tzx-gpu-dma32-runtime
TimeoutStartSec=35
'''
files['etc/systemd/system/lightdm.service.d/95-dma32.conf'] = b'''[Unit]
Wants=tzx-gpu.service
After=tzx-gpu.service
[Service]
ExecStart=
ExecStart=/bin/sh /usr/local/lib/tzx-gpu-dma32/tzx-gpu-lightdm
'''
files['etc/systemd/system/tzx-gpu-dma32-health.service'] = b'''[Unit]
Description=Check TZX DMA32 GPU desktop after boot
ConditionKernelVersion=7.3.3-tzx-a523-accel1
ConditionPathExists=/var/lib/tzx/gpu-qualified
Wants=lightdm.service
After=lightdm.service tzx-gpu.service
OnFailure=tzx-gpu-dma32-fallback.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-gpu-dma32/tzx-gpu-dma32-boot-check.py
TimeoutStartSec=100
[Install]
WantedBy=multi-user.target
'''
files['etc/systemd/system/tzx-gpu-dma32-fallback.service'] = b'''[Unit]
Description=Disable unqualified TZX GPU and restore software desktop
After=tzx-gpu.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-gpu-dma32/tzx-gpu-dma32-disable.py
TimeoutStartSec=85
'''
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
(stage / 'FILES.json').write_text(json.dumps(manifest, indent=2) + '\n', newline='\n')
for name in ('install_gpu_dma32_runtime.py', 'rollback_gpu_dma32_runtime.py'):
    data = (root / 'firmware' / name).read_bytes()
    compile(data, name, 'exec')
    (stage / name).write_bytes(data)
archive = out / 'gpu-dma32-runtime.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install_gpu_dma32_runtime.py',
                        'rollback_gpu_dma32_runtime.py']):
        package.add(stage / name, arcname=name, recursive=False)
(out / 'MANIFEST.json').write_text(json.dumps({
    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'files': manifest, 'kernel': release + ' #4',
    'status': 'staged_not_installed_manual_and_boot_validation_required',
    'gpu_qualified': False, 'full_CPU_memory_GiB': 4,
    'gpu_clock_Hz': 200000000, 'voltage_changed': False}, indent=2) + '\n', newline='\n')
print('GPU_DMA32_RUNTIME_STAGED', len(files), archive.stat().st_size)
