"""Package an additive startup overlay from exact original-unit source pins."""
import hashlib
import io
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
baseline = json.loads((root/'evidence/boot-streamline-baseline.json').read_text(encoding='utf-8'))
extra = json.loads((root/'evidence/boot-streamline-v3-source-input.json').read_text(encoding='utf-8'))
for name, item in baseline['files'].items(): assert extra['files'][name]['sha256'] == item['sha256'], name
baseline['files'].update(extra['files'])
folder = root/'build/boot-streamline'
folder.mkdir(exist_ok=True)
prefix = '/usr/local/lib/tzx-boot-streamline-v6/'
files = {prefix+'runtime.py': (root/'firmware/tzx_boot_streamline.py').read_bytes(),
         prefix+'observer.py': (root/'firmware/tzx_boot_streamline_observer.py').read_bytes()}
unit = '/etc/systemd/system/'
early = baseline['files'][unit+'tzx-early-performance-check.service']['text']
needle = 'Requires=tzx-thermal.service tzx-cpub.service\nAfter=tzx-thermal.service tzx-cpub.service\n'
assert early.count(needle) == 1
files[unit+'tzx-early-performance-check.service'] = early.replace(needle,
    'DefaultDependencies=no\nRequires=tzx-cpub.service\n'
    'After=tzx-cpub.service systemd-remount-fs.service\n'
    'Conflicts=shutdown.target\nBefore=shutdown.target\n').encode()
# The soft-off handler validates the original CPU supply at registration.
# Register it before CPU DVFS raises that supply; shutdown still restores it.
files[unit+'tzx-cpu-dvfs.service.d/99-boot-streamline.conf'] = b'''[Unit]
Requires=tzx-pmic-poweroff.service
After=tzx-pmic-poweroff.service
'''
for name, operation in (('tzx-boot-panel-handoff', 'handoff'), ('tzx-gpu', 'gpu'),
                        ('tzx-emmc-hs', 'emmc')):
    text = '[Service]\nExecStart=\nExecStart=/usr/bin/python3 -u '+prefix+'runtime.py '+operation+'\n'
    if operation == 'emmc':
        text = baseline['files'][unit+'tzx-emmc-hs.service']['text']
        needle = 'After=tzx-dram-gpu-health.service tzx-screen-health.service tzx-cpu-dvfs.service tzx-gpu-performance.service tzx-emmc-performance.service\n'
        assert text.count(needle) == 1
        text = text.replace(needle, 'After=tzx-thermal.service tzx-early-performance-check.service tzx-cpu-dvfs.service\nBefore=tzx-gpu.service lightdm.service\n')
        text = text.replace('Requires=tzx-thermal.service\n',
                            'Requires=tzx-thermal.service tzx-early-performance-check.service tzx-cpu-dvfs.service\n')
        text = text.replace('ExecStart=/usr/bin/python3 -u /usr/local/lib/tzx-emmc-hs/runtime.py run',
                            'ExecStart=/usr/bin/python3 -u '+prefix+'runtime.py emmc')
        files[unit+name+'.service'] = text.encode()
    else:
        files[unit+name+'.service.d/99-boot-streamline.conf'] = text.encode()
files[unit+'tzx-bluetooth-late.timer'] = b'''[Unit]
Description=Attach Bluetooth after graphical startup without delaying it
DefaultDependencies=no
After=lightdm.service
Before=shutdown.target
Conflicts=shutdown.target
[Timer]
OnActiveSec=3s
AccuracySec=1s
Unit=tzx-bluetooth.service
[Install]
WantedBy=graphical.target
'''
files[unit+'tzx-boot-streamline-observer.service'] = ('''[Unit]
Description=Record first desktop processes independently of desktop startup
After=lightdm.service
[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=80s
ExecStart=/usr/bin/python3 '''+prefix+'''observer.py
[Install]
WantedBy=graphical.target
''').encode()
sha = lambda data: hashlib.sha256(data).hexdigest()
for component in ('tzx-emmc-hs', 'tzx-performance-mode'):
    name = '/usr/local/lib/'+component+'/manifest.json'
    value = json.loads(baseline['files'][name]['text'])
    for filename, digest in value['files'].items():
        if filename in files:
            assert digest == baseline['files'][filename]['sha256'], filename
            value['files'][filename] = sha(files[filename])
    files[name] = (json.dumps(value, indent=2)+'\n').encode()
replaced = {name: item for name, item in baseline['files'].items() if name in files}
manifest = dict(profile='TZX-A523-additive-boot-streamline-v6',
    baseline_boot_id=baseline['boot_id'], expected_toc0_sha256='3031c2e408edb41dab4ab0f35171bf9ea3398842bfd2c653c8017149b13791ba',
    original_sources={name: item['sha256'] for name, item in baseline['files'].items() if name not in replaced},
    replaced_files={name: dict(sha256=item['sha256'], mode=item['mode']) for name, item in replaced.items()},
    files={name: sha(data) for name, data in files.items()},
    bluetooth_boot_link=baseline['bluetooth_boot_link'])
files[prefix+'manifest.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
path = root/'build/boot-streamline-stage.tar.gz'
with tarfile.open(path, 'w:gz') as archive:
    for name, data in files.items():
        member = tarfile.TarInfo(name.lstrip('/'))
        member.size, member.mode = len(data), 0o644
        archive.addfile(member, io.BytesIO(data))
(folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print('BOOT_STREAMLINE_ADDITIVE_STAGE', len(files), path.stat().st_size, sha(path.read_bytes()), flush=True)
