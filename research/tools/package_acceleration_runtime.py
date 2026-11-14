"""Stage accel1 modules and boot-only overrides while preserving periph1."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root / 'build/acceleration-kernel'
stage = out / 'runtime'
old = '7.3.3-tzx-a523-periph1'
release = '7.3.3-tzx-a523-accel1'
files = {}
units = {}
packages = [root/'build/peripheral-kernel/graphics-runtime.tar.gz',
            root/'build/peripheral-kernel/bluetooth-runtime.tar.gz',
            root/'build/audio-codec/audio-runtime.tar.gz']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def translate(text):
    for before, after in [(old, release), ('tzx-peripherals-periph1', 'tzx-peripherals-accel1'),
                          ('/usr/local/lib/tzx-display', '/usr/local/lib/tzx-accel-display'),
                          ('/usr/local/lib/tzx-bluetooth', '/usr/local/lib/tzx-accel-bluetooth'),
                          ('/usr/local/lib/tzx-audio', '/usr/local/lib/tzx-accel-audio')]:
        text = text.replace(before, after)
    return text


for package in packages:
    with tarfile.open(package) as archive:
        manifest = json.load(archive.extractfile('FILES.json'))
        for name, digest in manifest.items():
            data = archive.extractfile(name).read()
            assert sha(data) == digest, (package, name)
            if name.startswith('lib/modules/') or name.startswith('boot/config-'):
                continue
            if name.startswith('etc/systemd/system/'):
                if name.endswith('.service'):
                    units[Path(name).name] = translate(data.decode())
                continue  # Current common drop-ins are already installed and preserved.
            if name == 'usr/local/sbin/tzx-peripherals-dispatch' or name.startswith('etc/'):
                continue
            target = translate('/' + name).lstrip('/')
            if not name.endswith(('.ko', '.fw')):
                data = translate(data.decode()).encode()
            files[target] = data

module_root = out/'modules/lib/modules'/release
assert module_root.is_dir()
for path in module_root.rglob('*'):
    if path.name in ('source', 'build'):
        continue
    if path.is_file() and not path.is_symlink():
        files['lib/modules/'+release+'/'+path.relative_to(module_root).as_posix()] = path.read_bytes()
for path in (out/'peripherals').glob('*.ko'):
    data = path.read_bytes()
    assert (release + ' ').encode() in data, path
    if path.name in ['tzx_gsl3670.ko', 'tzx_touch_runtime.ko', 'tzx_wifi_runtime.ko',
                     'aic8800_bsp.ko', 'aic8800_fdrv.ko']:
        target = 'usr/local/lib/tzx-peripherals-accel1/'+path.name
    else:
        target = 'lib/modules/'+release+'/extra/'+path.name
    files[target] = data
assert len(list((out/'peripherals').glob('*.ko'))) == 11

# Rebuild hash guards from the new matching modules.
for component, name in [('display', 'tzx_display.ko'), ('bluetooth', 'tzx_bt_runtime.ko')]:
    target = 'lib/modules/'+release+'/extra/'+name
    files['usr/local/lib/tzx-accel-'+component+'/MODULE.sha256'] = (
        sha(files[target])+'  /'+target+'\n').encode()
audio = ['tzx_codec_driver.ko', 'tzx_generic_dmaengine_pcm.ko', 'tzx_pcm_dmaengine.ko']
files['usr/local/lib/tzx-accel-audio/MODULES.sha256'] = ''.join(
    sha(files['lib/modules/'+release+'/extra/'+name])+'  /lib/modules/'+release+'/extra/'+name+'\n'
    for name in audio).encode()
for wrapper in ['tzx-touch-runtime-test.sh', 'tzx-wifi-runtime-test.sh']:
    key = 'usr/local/lib/tzx-peripherals-accel1/'+wrapper
    lines = files[key].decode().splitlines(True)
    import re
    for index, line in enumerate(lines):
        for name in ['tzx_gsl3670.ko', 'tzx_touch_runtime.ko', 'tzx_wifi_runtime.ko']:
            if 'sha256sum' in line and name in line:
                lines[index] = re.sub(r"(?<= = ')[0-9a-f]{64}(?=')",
                    sha(files['usr/local/lib/tzx-peripherals-accel1/'+name]), line)
    files[key] = ''.join(lines).encode()

commands = {
    'tzx-touch.service': ('/bin/sh /usr/local/lib/tzx-peripherals-accel1/tzx-touch-runtime-test.sh', ' start', ' stop'),
    'tzx-wifi.service': ('/bin/sh /usr/local/lib/tzx-peripherals-accel1/tzx-wifi-runtime', ' start', ' stop'),
    'tzx-display.service': ('/bin/sh /usr/local/lib/tzx-accel-display/tzx-display-runtime', ' start', ' stop'),
    'tzx-audio.service': ('/bin/sh /usr/local/lib/tzx-accel-audio/tzx-audio-runtime', ' start', ' stop'),
    'tzx-battery.service': ('/sbin/modprobe', ' tzx_battery', ' -r tzx_battery'),
}
overrides = {}
for unit, (command, start, stop) in commands.items():
    overrides[unit] = ('[Unit]\nConditionKernelVersion=\nConditionKernelVersion='+release+
        '\n[Service]\nExecStart=\nExecStart='+command+start+'\nExecStop=\nExecStop='+command+stop+'\n')
for unit in ['tzx-bt-hardware.service', 'tzx-bluetooth.service']:
    # Replace the complete start command, retaining service dependencies/type.
    text = units[unit]
    start = next(line for line in text.splitlines() if line.startswith('ExecStart='))
    overrides[unit] = ('[Unit]\nConditionKernelVersion=\nConditionKernelVersion='+release+
                       '\n[Service]\nExecStart=\n'+start+'\n')
files['usr/local/lib/tzx-accel/overrides.json'] = (json.dumps(overrides, indent=2)+'\n').encode()
files['usr/lib/systemd/system-generators/tzx-acceleration-runtime'] = b'''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
if os.uname().release != '7.3.3-tzx-a523-accel1':
    raise SystemExit(0)
if Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() != '3e01ff55454d20202010209170281b59':
    raise SystemExit(1)
for unit,text in json.loads(Path('/usr/local/lib/tzx-accel/overrides.json').read_text()).items():
    directory=Path(sys.argv[1])/(unit+'.d')
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'50-tzx-accel.conf').write_text(text)
'''
files['etc/modprobe.d/tzx-acceleration-manual.conf'] = b'''# Load the untested GPU and its power controller only during explicit testing.
blacklist panfrost
blacklist sun55i_pck600
'''
files['boot/config-'+release] = (out/'kernel.config').read_bytes()
manifest = {name: sha(data) for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
(stage/'FILES.json').write_text(json.dumps(manifest, indent=2)+'\n')
installer = '''import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
assert os.uname().release in ['7.3.3-tzx-a523-periph1','7.3.3-tzx-a523-accel1']
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('usr/local/lib/tzx-accel','usr/local/lib/tzx-peripherals-accel1/',
        'lib/modules/7.3.3-tzx-a523-accel1/','boot/config-7.3.3-tzx-a523-accel1',
        'usr/lib/systemd/system-generators/tzx-acceleration-runtime','etc/modprobe.d/tzx-acceleration-manual.conf'))
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name;target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tzx-new')
    temporary.write_bytes((stage/name).read_bytes())
    temporary.chmod(0o755 if 'system-generators/' in name else 0o644)
    temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
subprocess.run(['depmod','-a','7.3.3-tzx-a523-accel1'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
os.sync()
print('ACCEL_RUNTIME_INSTALLED_HASH_VERIFIED',len(files))
'''
compile(installer, 'install.py', 'exec')
(stage/'install.py').write_text(installer, newline='\n')
archive = out/'acceleration-runtime.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install.py']):
        package.add(stage/name, arcname=name, recursive=False)
(out/'acceleration-runtime.json').write_text(json.dumps({
    'files': manifest, 'archive_sha256': sha(archive.read_bytes()), 'boot_verified': False,
    'periph1_files_preserved': True, 'gpu_automatic_load_enabled': False}, indent=2)+'\n')
print('ACCEL_RUNTIME_PACKAGED',len(files),archive.stat().st_size,sha(archive.read_bytes()))
