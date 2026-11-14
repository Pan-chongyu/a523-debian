"""Reboot only after the candidate, file audit, and current desktop are ready."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
root = Path('/var/lib/tzx')
state = json.loads((root/'screen-installed.json').read_text())
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if state['state'] == 'poweron_verified_enabled_pending_reboot':
    assert state['installed_boot_id'] == boot and state['poweron_installed_boot_id'] == boot
    assert json.loads((root/'screen-poweron-test.json').read_text())['result'] == 'PASS'
    assert json.loads((root/'screen-boot-kernel-installed.json').read_text())['state'] == 'selected_pending_reboot'
elif state['state'] == 'standby_verified_enabled_pending_reboot':
    assert state['installed_boot_id'] == boot and state['standby_installed_boot_id'] == boot
    proof = json.loads((root/'screen-standby-test.json').read_text())
    assert proof['boot_id'] == boot and proof['result'] == 'PASS'
elif state['state'] == 'doublebuffer_verified_enabled_pending_reboot':
    assert state['installed_boot_id'] == boot and state['doublebuffer_installed_boot_id'] == boot
    assert json.loads((root/'screen-doublebuffer-test.json').read_text())['result'] == 'PASS'
elif state['state'] == 'vblank_verified_enabled_pending_reboot':
    assert state['installed_boot_id'] == boot and state['vblank_installed_boot_id'] == boot
    assert json.loads((root/'screen-vblank-test.json').read_text())['result'] == 'PASS'
    assert json.loads((root/'screen-pageflip-test.json').read_text())['result'] == 'PASS'
elif state.get('brightness_persistence') == 'pending_actual_reboot':
    assert state['state'] == 'manual_display_and_actual_autostart_verified'
    assert state['brightness_fix_installed_boot_id'] == boot
else:
    assert state['state'] == 'manual_display_verified_enabled_pending_reboot'
    assert state['installed_boot_id'] == boot
for name, entry in state['files'].items():
    assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == entry['sha256'], name
unit = ('tzx-screen-poweron-boot-files.service' if state.get('profile') == 'screen-functions-5-poweron' else
        'tzx-screen-standby-boot-files.service' if state.get('profile') == 'screen-functions-4-standby'
        else 'tzx-screen-boot-files.service')
props = subprocess.check_output(['systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus'], text=True)
assert all(value in props for value in ('ActiveState=inactive', 'Result=success', 'ExecMainStatus=0'))
journal = subprocess.check_output(['journalctl', '-b', '-u', unit, '-o', 'cat', '--no-pager'], text=True)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in journal
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
assert json.loads((root/'screen-boot-health.json').read_text())['boot_id'] == boot
assert not (root/'screen-boot-pending.json').exists()
intent = {'previous_boot_id': boot, 'brightness': int(Path('/sys/class/backlight/tzx-panel/brightness').read_text()),
          'orientation': json.loads(Path('/home/debian/.config/tzx-screen.json').read_text())['rotation'],
          'file_audit': 'PASS', 'user_confirmed_controls_and_pattern': True}
path = root/'screen-reboot-intent.json'
with path.open('w') as f:
    json.dump(intent, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
os.sync()
subprocess.run(['systemd-run', '--unit=tzx-screen-validated-reboot', '--on-active=3s',
                '/usr/bin/systemctl', 'reboot'], check=True, timeout=12)
print('TZX_SCREEN_REBOOT_INTENT', json.dumps(intent), flush=True)
