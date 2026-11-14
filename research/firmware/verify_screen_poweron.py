"""Verify first-frame power gating and landscape defaults at the greeter boundary."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--after-boot', action='store_true')
a = p.parse_args()
assert os.geteuid() == 0
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
params = Path('/sys/module/tzx_display/parameters')
assert (params/'screen_revision').read_text().strip() == 'screen-functions-5-poweron'
panel = {name: (params/name).read_text().strip() for name in
         ('panel_frame_committed', 'panel_power_phase', 'panel_power_status', 'panel_backlight_blocked',
          'screen_buffer_errors', 'screen_buffer_commits', 'screen_panel_errors')}
assert panel['panel_frame_committed'] == 'Y' and panel['panel_power_phase'] == '8', panel
assert int(panel['panel_power_status']) & 16
assert panel['screen_buffer_errors'] == panel['screen_panel_errors'] == '0'
assert int(panel['screen_buffer_commits']) > 0
setup = json.loads(Path('/var/lib/tzx/screen-display-setup.json').read_text())
assert setup['boot_id'] == boot and setup['result'] == 'PASS', setup
# This sample is taken by LightDM before xrandr setup and before user login.
assert 'current 1280 x 800' in setup['initial_query'] and ' right (' in setup['initial_query']
assert '0.000000, 1.000000, 0.000000, -1.000000, 0.000000, 1.000000' in setup['touch_properties']
env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
query = subprocess.check_output(['xrandr', '--query'], env=env, text=True, timeout=10)
assert 'current 1280 x 800' in query and ' right (' in query
assert json.loads(Path('/etc/tzx-screen/defaults.json').read_text())['rotation'] == 'right'
assert json.loads(Path('/home/debian/.config/tzx-screen.json').read_text())['rotation'] == 'right'
log = subprocess.check_output(['dmesg'], text=True)
assert 'panel bias PH18 then PH19, backlight held off' in log
assert 'first frame committed; backlight release permitted' in log
startup = [row for row in log.splitlines() if any(message in row for message in
           ('panel bias PH18 then PH19', 'backlight PWM0 PD23', 'first frame committed',
            'Console: switching to colour frame buffer device'))]
prepared = next(row for row in startup if 'backlight PWM0 PD23' in row)
first_frame = next(row for row in startup if 'first frame committed' in row)
assert 'regs=00000001,00000000,' in prepared, prepared
assert startup.index(prepared) < startup.index(first_frame)
config = gzip.decompress(Path('/proc/config.gz').read_bytes())
enabled = b'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y\n' in config
fbcon = Path('/sys/class/graphics/fbcon/rotate').read_text().strip()
if a.after_boot:
    assert enabled and fbcon == '1'
    assert setup['fbcon_rotate'] == '1'
    assert any('160x50' in row for row in startup if 'Console:' in row), startup
    assert hashlib.sha256(config).hexdigest() == '428ec704c7c2e2d1a457dd421f232ed2082850229900f67bc1902c49fb92cf59'
assert 'Mali-G57' in subprocess.check_output(['glxinfo', '-B'], env=env, text=True, timeout=12)
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
proof = {'boot_id': boot, 'result': 'PASS', 'panel': panel, 'desktop': query,
         'before_greeter': setup, 'kernel_console_rotation_enabled': enabled,
         'startup_log': startup, 'fbcon_rotate': fbcon,
         'qualification': 'actual_kernel_reboot' if a.after_boot else 'manual_driver_and_Xorg_reload'}
Path('/var/lib/tzx/screen-poweron-test.json').write_text(json.dumps(proof, indent=2)+'\n')
print('TZX_SCREEN_POWERON_AND_RIGHT_LANDSCAPE_PASS', json.dumps(proof), flush=True)
