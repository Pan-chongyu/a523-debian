"""Create the independent screen runtime; do not modify original display/GPU files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--name', choices=('screen-runtime', 'screen-runtime-brightness-save',
                                 'screen-runtime-vblank', 'screen-runtime-doublebuffer',
                                 'screen-runtime-standby'), default='screen-runtime')
a = p.parse_args()
standby = a.name == 'screen-runtime-standby'
vblank = a.name in ('screen-runtime-vblank', 'screen-runtime-doublebuffer', 'screen-runtime-standby')
doublebuffer = a.name in ('screen-runtime-doublebuffer', 'screen-runtime-standby')
profile = 'screen-functions-4-standby' if standby else 'screen-functions-3-doublebuffer' if doublebuffer else 'screen-functions-2-vblank'
out = root/('build/screen-standby' if standby else 'build/screen-doublebuffer-r2' if doublebuffer else 'build/screen-vblank' if vblank else 'build/screen-complete')
runtime = root/'firmware/tzx_screen_runtime.py'
if vblank:
    text = runtime.read_text()
    assert text.count("MODULE_SHA = '4c565e31c3ad5bbef6900b95a79bee651026881a0421f2f0049f1f9135bd5491'") == 1
    text = text.replace('4c565e31c3ad5bbef6900b95a79bee651026881a0421f2f0049f1f9135bd5491',
                        hashlib.sha256((out/'tzx_display.ko').read_bytes()).hexdigest())
    assert text.count('qualified = a.trial or QUALIFIED.exists()') == 1
    text = text.replace('qualified = a.trial or QUALIFIED.exists()',
                        "qualified = a.trial or (QUALIFIED.exists() and "
                        "json.loads(QUALIFIED.read_text()).get('profile') == '"+profile+"')")
    text = text.replace('screen-functions-1', profile)
    if doublebuffer:
        marker = "        gpu_health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())"
        assert text.count(marker) == 1
        text = text.replace(marker,
                            "        assert int(Path('/sys/module/tzx_display/parameters/screen_buffer_errors').read_text()) == 0\n"
                            "        assert int(Path('/sys/module/tzx_display/parameters/screen_buffer_commits').read_text()) > 0\n"+marker)
    if standby:
        marker = "        gpu_health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())"
        assert text.count(marker) == 1
        text = text.replace(marker,
                            "        assert int(Path('/sys/module/tzx_display/parameters/screen_panel_errors').read_text()) == 0\n"
                            "        assert Path('/sys/module/tzx_display/parameters/screen_panel_sleeping').read_text().strip() == 'N'\n"+marker)
    runtime = out/'runtime.py'
    with runtime.open('x', newline='\n') as f:
        f.write(text)
mapping = {
    'usr/local/lib/tzx-screen/tzx_display.ko': (out/'tzx_display.ko', 0o644),
    'usr/local/lib/tzx-screen/runtime.py': (runtime, 0o644),
    'usr/local/bin/tzx-screen': (root/'firmware/tzx_screen.py', 0o755),
    'usr/share/applications/tzx-screen.desktop': (root/'firmware/tzx-screen.desktop', 0o644),
    'etc/xdg/autostart/tzx-screen-orientation.desktop': (root/'firmware/tzx-screen-orientation.desktop', 0o644),
    'etc/systemd/system/tzx-screen-health.service': (root/'firmware/tzx-screen-health.service', 0o644),
    'etc/systemd/system/tzx-display.service.d/98-screen.conf': (root/'firmware/tzx-screen-display.conf', 0o644),
}
record = {'cid': '3e01ff55454d20202010209170281b59', 'kernel': '7.3.3-tzx-a523-accel1 #5',
          'raw_boot_changed': False, 'original_display_and_GPU_retained': True, 'files': {}}
package = out/(a.name+'.tar.gz')
with package.open('xb') as f, tarfile.open(fileobj=f, mode='w:gz') as archive:
    for name, (source, mode) in mapping.items():
        data = source.read_bytes()
        entry = tarfile.TarInfo(name)
        entry.size = len(data)
        entry.mode = mode
        entry.mtime = 0
        archive.addfile(entry, io.BytesIO(data))
        record['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'mode': mode}
record['package_sha256'] = hashlib.sha256(package.read_bytes()).hexdigest()
manifest = out/('FILES.json' if a.name == 'screen-runtime' else a.name+'-FILES.json')
assert not manifest.exists()
manifest.write_text(json.dumps(record, indent=2)+'\n', newline='\n')
print('SCREEN_RUNTIME_PACKAGED', json.dumps(record))
