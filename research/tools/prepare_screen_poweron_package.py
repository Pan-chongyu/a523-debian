"""Package the new display revision without altering the frozen v4 artifacts."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
out = root/'build/screen-poweron'
module = (out/'tzx_display.ko').read_bytes()
module_sha = hashlib.sha256(module).hexdigest()
runtime = (root/'build/screen-standby/runtime.py').read_text()
runtime = runtime.replace('screen-functions-4-standby', 'screen-functions-5-poweron')
runtime = runtime.replace('d98717cb1079be9d0cc18121d9a900e3b353870c3b064128e442b6537fa5a10c', module_sha)
marker = "        gpu_health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())"
assert runtime.count(marker) == 1
runtime = runtime.replace(marker, """        panel = {name: Path('/sys/module/tzx_display/parameters', name).read_text().strip()
                 for name in ('panel_frame_committed', 'panel_power_phase', 'panel_power_status',
                              'panel_backlight_blocked')}
        assert panel['panel_frame_committed'] == 'Y' and panel['panel_power_phase'] == '8'
        assert int(panel['panel_power_status']) & 16
        setup = json.loads(Path('/var/lib/tzx/screen-display-setup.json').read_text())
        assert setup['boot_id'] == BOOT and setup['result'] == 'PASS'
        assert 'current 1280 x 800' in result.stdout
"""+marker)
runtime = runtime.replace("'GPU': 'Mali-G57', 'xrandr': result.stdout}",
                          "'GPU': 'Mali-G57', 'xrandr': result.stdout, 'panel': panel, 'display_setup': setup}")
(out/'runtime.py').write_text(runtime, newline='\n')
app = (root/'firmware/tzx_screen.py').read_text()
old = """    remembered = None
    if CONFIG.exists():
        remembered = json.loads(CONFIG.read_text()).get('rotation')
    if remembered in MATRICES:
        try:
            rotate(remembered)"""
new = """    # Every new session starts in the board's right-landscape default.
    # Runtime rotation controls still work and the daemon keeps touch aligned.
    defaults = Path('/etc/tzx-screen/defaults.json')
    default = json.loads(defaults.read_text()).get('rotation', 'right') if defaults.exists() else 'right'
    if default in MATRICES:
        try:
            rotate(default)"""
assert app.count(old) == 1
app = app.replace(old, new).replace('Restoring screen orientation:', 'Default screen orientation:')
app = app.replace("    label = Gtk.Label(label='屏幕亮度')", "    label = Gtk.Label(label='屏幕亮度（开机默认横屏向右）')")
(out/'tzx_screen.py').write_text(app, newline='\n')
files = {}
with tarfile.open(root/'build/screen-standby/screen-runtime-standby.tar.gz', 'r:gz') as archive:
    for member in archive.getmembers():
        assert member.isfile()
        files[member.name] = (archive.extractfile(member).read(), member.mode)
files['usr/local/lib/tzx-screen/tzx_display.ko'] = (module, 0o644)
files['usr/local/lib/tzx-screen/runtime.py'] = (runtime.encode(), 0o644)
files['usr/local/bin/tzx-screen'] = (app.encode(), 0o755)
files['usr/local/lib/tzx-screen/display-setup.py'] = ((root/'firmware/tzx_screen_display_setup.py').read_bytes(), 0o755)
files['usr/local/lib/tzx-screen/lightdm.py'] = ((root/'firmware/tzx_screen_lightdm.py').read_bytes(), 0o755)
files['usr/local/lib/tzx-screen/lightdm.conf'] = (b'''[Seat:*]
xserver-command=X -configdir /usr/local/lib/tzx-screen/xorg.conf.d
display-setup-script=/usr/local/lib/tzx-screen/display-setup.py
autologin-user=debian
autologin-user-timeout=0
user-session=xfce
greeter-session=lightdm-gtk-greeter
''', 0o644)
# Byte-identical copy of the existing qualified GPU configuration.
files['usr/local/lib/tzx-screen/xorg.conf.d/20-tzx-display.conf'] = ((root/'firmware/30-tzx-acceleration.conf').read_bytes(), 0o644)
files['usr/local/lib/tzx-screen/xorg.conf.d/90-tzx-landscape.conf'] = (b'''Section "Monitor"
    Identifier "DSI-1"
    Option "PreferredMode" "800x1280"
    Option "Rotate" "right"
    Option "Primary" "true"
EndSection

Section "InputClass"
    Identifier "TZX GSL3670 right landscape"
    MatchProduct "TZX GSL3670 candidate"
    MatchIsTouchscreen "on"
    Option "TransformationMatrix" "0 1 0 -1 0 1 0 0 1"
EndSection
''', 0o644)
files['etc/systemd/system/lightdm.service.d/98-screen-landscape.conf'] = (b'''[Service]
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/lib/tzx-screen/lightdm.py
''', 0o644)
files['etc/tzx-screen/defaults.json'] = (b'{"rotation": "right", "new_session_policy": "always_default"}\n', 0o644)
package = out/'screen-runtime-poweron.tar.gz'
with tarfile.open(package, 'w:gz') as archive:
    for name, (data, mode) in files.items():
        member = tarfile.TarInfo(name)
        member.size, member.mode = len(data), mode
        archive.addfile(member, io.BytesIO(data))
manifest = {'profile': 'screen-functions-5-poweron',
            'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
            'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'mode': mode}
                      for name, (data, mode) in files.items()}}
(out/'FILES.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps({'package_sha256': manifest['package_sha256'], 'module_sha256': module_sha,
                  'files': len(files)}, indent=2))
