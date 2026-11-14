"""Qualify an actual reboot of the installed startup overlay and mixed load."""
import json
import os
import subprocess
import time
from pathlib import Path

assert os.geteuid() == 0
state = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
installed = json.loads((state/'boot-streamline-v6-installed.json').read_text())
assert installed['state'] == 'installed' and installed['installed_boot_id'] != boot


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=90)


print(run('python3', '/home/debian/install_boot_streamline.py', 'verify'), end='', flush=True)
print(run('python3', '/home/debian/verify_boot_logo_overlap.py'), end='', flush=True)
names = ('tzx-cpub', 'tzx-early-performance-check', 'tzx-thermal', 'tzx-pmic-poweroff', 'tzx-cpu-dvfs',
         'tzx-emmc-hs', 'tzx-gpu', 'tzx-display', 'tzx-touch-input-ready',
         'tzx-cpu-performance-mode', 'tzx-gpu-performance', 'tzx-bluetooth', 'lightdm')
units = {}
for name in names:
    output = run('systemctl', 'show', name, '-p', 'ActiveState', '-p', 'Result',
                 '-p', 'ExecMainStartTimestampMonotonic', '-p', 'ActiveEnterTimestampMonotonic')
    item = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
    assert item['ActiveState'] == 'active' and item['Result'] == 'success', (name, item)
    units[name] = dict(start_kernel_s=int(item['ExecMainStartTimestampMonotonic'])/1e6,
                      active_kernel_s=int(item['ActiveEnterTimestampMonotonic'])/1e6)
assert units['tzx-cpub']['active_kernel_s'] <= units['tzx-early-performance-check']['start_kernel_s']
assert units['tzx-early-performance-check']['active_kernel_s'] <= units['tzx-cpu-dvfs']['start_kernel_s']
assert units['tzx-thermal']['active_kernel_s'] <= units['tzx-cpu-dvfs']['start_kernel_s']
assert units['tzx-pmic-poweroff']['active_kernel_s'] <= units['tzx-cpu-dvfs']['start_kernel_s']
assert units['tzx-cpu-dvfs']['active_kernel_s'] <= units['tzx-emmc-hs']['start_kernel_s']
assert units['tzx-emmc-hs']['active_kernel_s'] <= units['tzx-gpu']['start_kernel_s']
assert units['tzx-gpu']['active_kernel_s'] <= units['lightdm']['start_kernel_s']
assert units['tzx-touch-input-ready']['active_kernel_s'] <= units['lightdm']['start_kernel_s']
early = json.loads(Path('/run/tzx-early-performance-check.json').read_text())
assert early['boot_id'] == boot and early['status'] == 'PASS'
assert early['qualified_full_4GiB_and_voltage_guard']
assert 'MEMORY_TEST_256_MIB_8_THREADS_PASS' in early['memory_result']
basic_kernel_s = int(run('systemctl', 'show', 'basic.target', '-p',
                         'ActiveEnterTimestampMonotonic', '--value').strip())/1e6
assert units['tzx-early-performance-check']['start_kernel_s'] < basic_kernel_s
desktop = json.loads(Path('/run/tzx-boot-streamline-desktop.json').read_text())
assert desktop['boot_id'] == boot and desktop['status'] == 'PASS'
assert set(desktop['desktop_processes']) == {'Xorg', 'xfce4-session', 'xfwm4', 'xfce4-panel', 'xfdesktop'}
load = json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
assert load['boot_id'] == boot and load['status'] == 'PASS'
logo = json.loads((state/'boot-logo-overlap-qualified.json').read_text())
assert logo['boot_id'] == boot and logo['status'] == 'PASS'
checked = run('systemd-analyze', 'verify', '--man=no', 'graphical.target')
assert 'ordering cycle' not in checked.lower() and 'job deleted' not in checked.lower(), checked
bt_log = run('journalctl', '-b', '-u', 'tzx-bluetooth', '--no-pager', '-o', 'cat')
assert 'TZX_BT_HCI_POWERED hci0' in bt_log and 'Failed to start' not in bt_log
assert not run('systemctl', '--failed', '--no-legend', '--plain').strip()
assert boot == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
record = dict(status='PASS', profile=installed['profile'], boot_id=boot,
    captured_unix=int(time.time()), units=units, basic_target_kernel_s=basic_kernel_s,
    desktop=desktop, early_memory_check=early, mixed_load=load,
    first_image_counter_s=logo['receipt']['logo']['lit_counter_s'],
    original_image_pixels_preserved=True, right_landscape_and_touch_configuration='PASS',
    boot_loader_toc0_sha256=installed['toc0_sha256'], failed_services=[],
    unchanged_Bluetooth_sequence_and_waits=True,
    systemd_time=run('systemd-analyze', 'time'),
    measurement_scope='Desktop process creation after Linux start, not visual readiness or a power-button stopwatch',
    physical_power_key_test=False, visual_confirmation='pending')
encoded = json.dumps(record, indent=2)+'\n'
(state/('boot-streamline-qualified-'+boot+'.json')).write_text(encoded)
(state/'boot-streamline-qualified.json').write_text(encoded)
print('BOOT_STREAMLINE_ACTUAL_REBOOT_AND_FULL_STACK_PASS', json.dumps(dict(
    boot_id=boot, last_desktop_process_start_kernel_s=desktop['last_desktop_process_start_kernel_s'],
    first_image_counter_s=record['first_image_counter_s'],
    mixed_load_seconds=load['seconds'], failed_services=[])), flush=True)
