"""Stage an independent kernel, display, and peripheral module package."""
from pathlib import Path
import hashlib
import json
import re
import tarfile
import argparse

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--variant', choices=['graphics', 'peripheral'], default='graphics')
variant = parser.parse_args().variant
suffix = 'gfx1' if variant == 'graphics' else 'periph1'
out = root / ('build/graphics-kernel' if variant == 'graphics' else 'build/peripheral-kernel')
stage = out / 'runtime'
release = '7.3.3-tzx-a523-' + suffix
runtime = 'usr/local/lib/tzx-peripherals-' + suffix + '/'
files = {}
def digest(data): return hashlib.sha256(data).hexdigest()
def put(name, data):
    assert not name.startswith('/') and '..' not in Path(name).parts
    files[name] = data
for path in (out / 'modules/lib/modules' / release).rglob('*'):
    if path.name in ('build', 'source'):
        continue
    if path.is_file() and not path.is_symlink():
        put('lib/modules/' + release + '/' + path.relative_to(out / 'modules/lib/modules' / release).as_posix(), path.read_bytes())
module_target = 'lib/modules/' + release + '/extra/tzx_display.ko'
put(module_target, (out / 'tzx_display.ko').read_bytes())
for path in (out / 'peripherals').glob('*.ko'):
    put(runtime + path.name, path.read_bytes())
put(runtime + 'silead-seeedd1001-candidate.fw', (root / 'build/silead-seeedd1001-candidate.fw').read_bytes())
for name in ('tzx-touch-runtime-test.sh', 'tzx-wifi-runtime-test.sh'):
    text = (root / 'firmware' / name).read_text()
    text = text.replace("'7.3.3-tzx-a523'", repr(release)).replace('/home/debian/', '/' + runtime)
    for module in ('tzx_gsl3670.ko', 'tzx_touch_runtime.ko', 'tzx_wifi_runtime.ko'):
        replacement = out / 'peripherals' / module
        if module not in text:
            continue
        pattern = r"(?<= = ')[0-9a-f]{64}(?='\n)"
        lines = text.splitlines(True)
        for i, line in enumerate(lines):
            if 'sha256sum' in line and module in line:
                lines[i] = re.sub(pattern, digest(replacement.read_bytes()), line)
        text = ''.join(lines)
    put(runtime + name, text.encode())
text = (root / 'build/runtime-peripherals/usr/local/lib/tzx-peripherals/tzx-wifi-runtime').read_text()
put(runtime + 'tzx-wifi-runtime', text.replace('/usr/local/lib/tzx-peripherals', '/' + runtime.rstrip('/')).encode())
dispatcher = '''#!/bin/sh
set -eu
case "$(uname -r)" in
7.3.3-tzx-a523) runtime=/usr/local/lib/tzx-peripherals ;;
7.3.3-tzx-a523-gfx1) runtime=/usr/local/lib/tzx-peripherals-gfx1 ;;
7.3.3-tzx-a523-periph1) runtime=/usr/local/lib/tzx-peripherals-periph1 ;;
*) echo 'No verified peripherals for this kernel' >&2; exit 2;;
esac
case "$1" in
touch) shift; exec /bin/sh "$runtime/tzx-touch-runtime-test.sh" "$@" ;;
wifi) shift; exec /bin/sh "$runtime/tzx-wifi-runtime" "$@" ;;
*) exit 2;;
esac
'''
put('usr/local/sbin/tzx-peripherals-dispatch', dispatcher.encode())
for name, kind in (('tzx-touch.service', 'touch'), ('tzx-wifi.service', 'wifi')):
    text = (root / 'firmware' / name).read_text()
    text = re.sub(r'ExecStart=.*', f'ExecStart=/bin/sh /usr/local/sbin/tzx-peripherals-dispatch {kind} start', text)
    text = re.sub(r'ExecStop=.*', f'ExecStop=/bin/sh /usr/local/sbin/tzx-peripherals-dispatch {kind} stop', text)
    put('etc/systemd/system/' + name, text.encode())
put('etc/systemd/system/tzx-display.service', (root / 'firmware/tzx-display.service').read_text().replace('7.3.3-tzx-a523-gfx1', release).encode())
put('usr/local/lib/tzx-display/tzx-display-runtime', (root / 'firmware/tzx-display-runtime').read_text().replace('7.3.3-tzx-a523-gfx1', release).encode())
put('usr/local/lib/tzx-display/MODULE.sha256', (digest(files[module_target]) + '  /' + module_target + '\n').encode())
put('boot/config-' + release, (out / 'kernel.config').read_bytes())
if variant == 'peripheral':
    put('lib/modules/' + release + '/extra/tzx_battery.ko', (root/'build/battery-peripheral/tzx_battery.ko').read_bytes())
    put('etc/systemd/system/tzx-battery.service', (root/'firmware/tzx-battery.service').read_text().replace('7.3.3-tzx-a523-gfx1', release).encode())
manifest = {name: digest(data) for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
(stage / 'FILES.json').write_text(json.dumps(manifest, indent=2) + '\n')
installer = '''import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('usr/local/','lib/modules/7.3.3-tzx-a523-gfx1/','etc/systemd/system/tzx-','boot/config-'))
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name;target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tzx-new')
    temporary.write_bytes((stage/name).read_bytes());temporary.chmod(0o644);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
subprocess.run(['depmod','-a','7.3.3-tzx-a523-gfx1'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','tzx-touch.service','tzx-wifi.service','tzx-display.service'],check=True)
os.sync()
print('GRAPHICS_RUNTIME_INSTALLED_HASH_VERIFIED',len(files))
'''
installer = installer.replace('7.3.3-tzx-a523-gfx1', release)
(stage / 'install.py').write_text(installer, newline='\n')
archive = out / 'graphics-runtime.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install.py']):
        package.add(stage / name, arcname=name, recursive=False)
(out / 'graphics-runtime.json').write_text(json.dumps({'files':manifest,'archive_sha256':digest(archive.read_bytes()),'boot_verified':False},indent=2)+'\n')
print('Packaged', len(files), 'files,', archive.stat().st_size, 'bytes', digest(archive.read_bytes()))
