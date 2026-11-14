"""Package the actually tested modules and guarded startup services."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
stage = ROOT / 'build/runtime-peripherals'
stage.mkdir(exist_ok=True)
runtime = 'usr/local/lib/tzx-peripherals/'
files = {}
for name in ('tzx_gsl3670.ko', 'tzx_touch_runtime.ko', 'tzx_wifi_runtime.ko',
             'silead-seeedd1001-candidate.fw'):
    files[runtime + name] = (ROOT / 'build' / name).read_bytes()
for name in ('tzx-touch-runtime-test.sh', 'tzx-wifi-runtime-test.sh'):
    data = (ROOT / 'firmware' / name).read_text().replace('/home/debian/', '/' + runtime)
    files[runtime + name] = data.encode()
for name in ('tzx-touch.service', 'tzx-wifi.service'):
    files['etc/systemd/system/' + name] = (ROOT / 'firmware' / name).read_bytes()
cid = '3e01ff55454d20202010209170281b59'
mac = '02:' + ':'.join(f'{value:02x}' for value in hashlib.sha256(cid.encode()).digest()[:5])
files[runtime + 'tzx-wifi-runtime'] = (ROOT / 'firmware/tzx-wifi-runtime').read_text().replace('TZX_STABLE_MAC', mac).encode()
archive = ROOT / 'build/radxa-aic-candidate.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == '851b86bdb43aadd82a7c3e774a2c2a2ebf03f4519cfac7953fa9541b8fff00ec'
with tarfile.open(archive) as package:
    for item in package:
        name = item.name.removeprefix('./')
        if not item.isfile():
            continue
        if name.startswith('lib/firmware/'):
            assert '/' not in name.removeprefix('lib/firmware/')
            files[name] = package.extractfile(item).read()
        elif name.endswith(('/aic8800_bsp.ko', '/aic8800_fdrv.ko')):
            files[runtime + Path(name).name] = package.extractfile(item).read()
assert runtime + 'aic8800_bsp.ko' in files and runtime + 'aic8800_fdrv.ko' in files
for name, data in files.items():
    target = stage / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
(stage / 'FILES.json').write_text(json.dumps(manifest, indent=2) + '\n')
installer = '''import hashlib,json,os
from pathlib import Path
import subprocess
assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert subprocess.check_output(['uname','-r'],text=True).strip()=='7.3.3-tzx-a523'
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert name.startswith(('usr/local/lib/tzx-peripherals/','etc/systemd/system/tzx-','lib/firmware/'))
    assert '..' not in Path(name).parts and not Path(name).is_absolute()
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((stage/name).read_bytes())
    target.chmod(0o644)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
os.sync()
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','tzx-touch.service','tzx-wifi.service'],check=True)
print('INSTALLED_VERIFIED_RUNTIME_PERIPHERALS',len(files))
'''
(stage / 'install.py').write_text(installer, newline='\n')
output = ROOT / 'build/runtime-peripherals.tar.gz'
with tarfile.open(output, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install.py']):
        package.add(stage / name, arcname=name)
report = {'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
          'wifi_local_mac': mac, 'files': manifest, 'autostart_reboot_verified': False}
(ROOT / 'build/runtime-peripherals.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key:value for key,value in report.items() if key!='files'}, indent=2))
