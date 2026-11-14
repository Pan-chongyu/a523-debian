"""Package thermal/GPU modules with software rendering as the boot default."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root/'build/acceleration-hardware-safe'
stage = out/'runtime'
release = '7.3.3-tzx-a523-accel1'
files = {}
for directory, names in [
    ('gpu-acceleration', ['tzx_gpu_nodes.ko', 'tzx_display_domains.ko']),
    ('thermal-acceleration', ['tzx_thermal_nodes.ko', 'tzx_thermal_driver.ko'])]:
    for name in names:
        files['lib/modules/'+release+'/extra/'+name] = (root/'build'/directory/name).read_bytes()
prefix = 'usr/local/lib/tzx-accel-hardware/'
files[prefix+'MODULES.sha256'] = ''.join(
    hashlib.sha256(data).hexdigest()+'  /'+name+'\n'
    for name, data in sorted(files.items())).encode()
for name in ['tzx-acceleration-hardware', 'verify_gpu_render.py', 'verify_thermal_sensors.py']:
    files[prefix+name] = (root/'firmware'/name).read_bytes()
files['usr/share/drirc.d/90-tzx-a523.conf'] = (root/'firmware/tzx-mesa-kmsro.conf').read_bytes()
files['usr/local/lib/tzx-accel-gpu/xorg.conf.d/20-tzx-display.conf'] = (
    root/'firmware/30-tzx-acceleration.conf').read_bytes()
files['usr/local/lib/tzx-accel-gpu/lightdm.conf'] = b'''[Seat:*]
xserver-command=X -configdir /usr/local/lib/tzx-accel-gpu/xorg.conf.d
autologin-user=debian
autologin-user-timeout=0
user-session=xfce
greeter-session=lightdm-gtk-greeter
'''
descriptions = {
    'power': 'TZX P30 display power domain consumers',
    'thermal': 'TZX P30 calibrated five-channel temperature monitoring',
    'gpu': 'TZX P30 Mali-G57 Panfrost GPU at fixed 200 MHz',
}
for kind in ['power', 'thermal', 'gpu']:
    if kind == 'power':
        ordering = 'After=tzx-touch.service\nBefore=tzx-display.service\n'
    elif kind == 'thermal':
        ordering = 'After=systemd-sysctl.service tzx-touch.service\nBefore=tzx-gpu.service\n'
    else:
        ordering = ('ConditionPathExists=/var/lib/tzx/gpu-qualified\n'
                    'Requires=tzx-display.service tzx-accel-power.service tzx-thermal.service\n'
                    'After=tzx-display.service tzx-accel-power.service tzx-thermal.service\n'
                    'Before=lightdm.service\n')
    unit = 'tzx-accel-power.service' if kind == 'power' else 'tzx-'+kind+'.service'
    files['etc/systemd/system/'+unit] = (
        '[Unit]\nDescription='+descriptions[kind]+'\nConditionKernelVersion='+release+'\n'+ordering+
        '\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/sh /'+prefix+
        'tzx-acceleration-hardware '+kind+'\nExecStop=/bin/sh /'+prefix+
        'tzx-acceleration-hardware stop\nTimeoutStartSec=25\nTimeoutStopSec=5\n\n[Install]\nWantedBy=multi-user.target\n').encode()

overrides_path = root/'build/acceleration-kernel/runtime/usr/local/lib/tzx-accel/overrides.json'
overrides = json.loads(overrides_path.read_text())
overrides['tzx-display.service'] += '\n[Unit]\nRequires=tzx-accel-power.service\nAfter=tzx-accel-power.service\n'
overrides['lightdm.service'] = '''[Unit]
Wants=tzx-thermal.service
After=tzx-display.service tzx-thermal.service
[Service]
ExecStart=
ExecStart=/usr/sbin/lightdm
'''
files['usr/local/lib/tzx-accel/overrides.json'] = (json.dumps(overrides, indent=2)+'\n').encode()
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
for name, data in files.items():
    path = stage/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
(stage/'FILES.json').write_text(json.dumps(manifest, indent=2)+'\n')
installer = '''import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert not Path('/var/lib/tzx/gpu-qualified').exists(), 'GPU qualification has been withdrawn'
stage=Path(__file__).resolve().parent
files=json.loads((stage/'FILES.json').read_text())
for name,digest in files.items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert name.startswith(('lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_',
        'usr/local/lib/tzx-accel','usr/share/drirc.d/90-tzx-a523.conf','etc/systemd/system/tzx-'))
    assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
for name,digest in files.items():
    target=Path('/')/name;target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tzx-new')
    temporary.write_bytes((stage/name).read_bytes());temporary.chmod(0o644);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
subprocess.run(['depmod','-a',os.uname().release],check=True)
# Keep the common Xorg config compatible with the saved periph1 fallback.
backup=Path('/root/tzx-recovery/periph1/20-tzx-display.conf')
assert backup.exists()
Path('/etc/X11/xorg.conf.d/20-tzx-display.conf').write_bytes(backup.read_bytes())
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemd-analyze','--man=no','verify','tzx-accel-power.service','tzx-thermal.service','tzx-gpu.service','lightdm.service'],check=True)
subprocess.run(['systemctl','enable','tzx-accel-power.service','tzx-thermal.service','tzx-gpu.service'],check=True)
os.sync()
print('ACCEL_HARDWARE_INSTALLED_HASH_VERIFIED',len(files))
'''
compile(installer, 'install.py', 'exec')
(stage/'install.py').write_text(installer, newline='\n')
archive = out/'acceleration-hardware.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for name in sorted([*files, 'FILES.json', 'install.py']):
        package.add(stage/name, arcname=name, recursive=False)
(out/'acceleration-hardware.json').write_text(json.dumps({
    'files': manifest, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'runtime_verified': False, 'autostart_reboot_verified': False,
    'boot_renderer': 'software', 'gpu_autostart_requires_qualification_marker': True,
    'gpu_qualified': False,
    'gpu_clock_hz': 200000000, 'gpu_voltage_changed': False,
    'gpu_shader_pixel_readback_verified': True, 'desktop_glamor_verified': False,
    'temperature_load_response_verified': True}, indent=2)+'\n')
print('ACCEL_HARDWARE_PACKAGED',len(files),archive.stat().st_size)
