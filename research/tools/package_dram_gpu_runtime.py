"""Stage exactly the modules used by the successful full-memory comparison."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root/'build/dram-gpu-runtime'
stage = out/'stage'
prefix = 'usr/local/lib/tzx-dram-gpu/'
files = {}
for source, target in [('build/gpu-dma32-aarch64/panfrost-dma32.ko', 'panfrost.ko'),
                       ('build/gpu-dma32-aarch64/tzx_display-dma32.ko', 'tzx_display.ko'),
                       ('firmware/tzx_dram_gpu_runtime.py', 'runtime.py'),
                       ('firmware/read_axp_dram_status.py', 'read_axp_dram_status.py'),
                       ('firmware/tzx_direct_io.py', 'tzx_direct_io.py')]:
    files[prefix+target] = (root/source).read_bytes()
assert hashlib.sha256(files[prefix+'panfrost.ko']).hexdigest() == 'ad4127adbd990361f89dfa65e3707927609f7eefedc766cd03dedb25f6ba97ae'
assert hashlib.sha256(files[prefix+'tzx_display.ko']).hexdigest() == '49faef93a64f7c4c24dcf330fa8d21c47f9681a848e83bd6716bbfa4643b4440'
display = (root/'build/acceleration-kernel/runtime/usr/local/lib/tzx-accel-display/tzx-display-runtime').read_text()
assert hashlib.sha256(display.encode()).hexdigest() == '8581c7f3367afb0bbf117332a070622240e64cde2c404389c3f2f765956d49da'
assert display.count('    modprobe tzx_display\n') == 1
display = display.replace('    modprobe tzx_display\n', '''    for tzx_dep in $(modinfo -F depends /usr/local/lib/tzx-dram-gpu/tzx_display.ko | tr ',' ' '); do
        modprobe "$tzx_dep"
    done
    insmod /usr/local/lib/tzx-dram-gpu/tzx_display.ko
''')
files[prefix+'display-runtime'] = display.encode()
files['etc/systemd/system/tzx-display.service.d/96-dram-gpu.conf'] = b'''[Unit]
OnFailure=tzx-dram-gpu-fallback.service
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-dram-gpu/runtime.py display-start
ExecStop=
ExecStop=/usr/bin/python3 /usr/local/lib/tzx-dram-gpu/runtime.py display-stop
TimeoutStartSec=65
'''
files['etc/systemd/system/tzx-gpu.service.d/96-dram-gpu.conf'] = b'''[Unit]
After=tzx-rtc-log.service
OnFailure=tzx-dram-gpu-fallback.service
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-dram-gpu/runtime.py gpu-start
TimeoutStartSec=55
'''
files['etc/systemd/system/lightdm.service.d/96-dram-gpu.conf'] = b'''[Unit]
Wants=tzx-gpu.service
After=tzx-gpu.service
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-dram-gpu/runtime.py lightdm
'''
files['etc/systemd/system/tzx-dram-gpu-health.service'] = b'''[Unit]
Description=Validate trained full-memory Mali-G57 desktop at boot
ConditionKernelVersion=7.3.3-tzx-a523-accel1
ConditionPathExists=/var/lib/tzx/gpu-qualified
After=lightdm.service tzx-gpu.service
Wants=lightdm.service
OnFailure=tzx-dram-gpu-fallback.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-dram-gpu/runtime.py health
TimeoutStartSec=100
[Install]
WantedBy=multi-user.target
'''
files['etc/systemd/system/tzx-dram-gpu-fallback.service'] = b'''[Unit]
Description=Revoke failed GPU startup and restore software display
After=tzx-gpu.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-dram-gpu/runtime.py fallback
TimeoutStartSec=150
'''
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
(stage/'FILES.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
archive = out/'dram-gpu-runtime.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in [*files, 'FILES.json']:
        package.add(stage/name, arcname=name, recursive=False)
with tarfile.open(archive, 'r:gz') as package:
    for name, digest in manifest.items():
        assert hashlib.sha256(package.extractfile(name).read()).hexdigest() == digest
report = {'archive_bytes': archive.stat().st_size,
          'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
          'files': manifest, 'status': 'staged only; repeat and reboot evidence required',
          'raw_boot_changes': False}
(out/'PACKAGE.json').write_text(json.dumps(report, indent=2)+'\n')
print('DRAM_GPU_RUNTIME_STAGED', json.dumps({'files': len(files), 'archive_sha256': report['archive_sha256']}))
