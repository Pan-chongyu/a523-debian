"""Qualify the retained-display child without rewriting historical parent proofs.

The physical boot buffer now contains logs. The older logo verifier's immutable
picture and stopped-DE assertions intentionally do not apply to this child.
Raw boot/asset CRCs, parent installed files and the real decoder receipt still do.
"""
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess
import time

assert os.geteuid() == 0
state = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
params = Path('/sys/module/tzx_display/parameters')
sha = lambda data: hashlib.sha256(data).hexdigest()


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=120)


def load(path):
    return json.loads(Path(path).read_text())


def atomic(path, obj):
    path = Path(path)
    temporary = path.with_name(path.name + '.console-proof')
    with temporary.open('w') as stream:
        os.fchmod(stream.fileno(), path.stat().st_mode & 0o777 if path.exists() else 0o600)
        stream.write(json.dumps(obj, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


installed = load(state/'screen-boot-console-installed.json')
assert installed['state'] == 'installed'
assert installed['installed_boot_id'] != boot
print(run('python3', '/home/debian/install_live_display.py', 'verify'), end='', flush=True)
# This invokes read-only verification of the compact layer and all installed
# parents, including every payload CRC, both GPTs, fallback, signed SRAM and art.
print(run('python3', '/home/debian/install_boot_compact.py', 'verify'), end='', flush=True)
module = sha(Path('/usr/local/lib/tzx-screen/tzx_display.ko').read_bytes())
assert module == installed['plan']['module_sha256']
values = {name: (params/name).read_text().strip() for name in (
    'screen_revision', 'panel_startup_revision', 'panel_startup_black',
    'panel_black_masks', 'panel_black_releases', 'panel_black_errors',
    'panel_boot_adopted', 'screen_buffer_errors', 'screen_panel_errors')}
assert values['screen_revision'] == 'screen-functions-5-poweron'
assert values['panel_startup_revision'] == 'black-until-committed-1'
assert values['panel_startup_black'] == 'N' and values['panel_boot_adopted'] == 'Y'
assert all(values[name] == '0' for name in ('panel_black_errors', 'screen_buffer_errors', 'screen_panel_errors'))
assert int(values['panel_black_releases']) > 0
adoption = load('/run/tzx-boot-console-adopt.json')
assert adoption['boot_id'] == boot and adoption['adopt']
assert all(adoption[name] is True for name in ('live_PWM_preserved', 'live_DSI_preserved', 'panel_rail_preserved'))
logo = load(state/'boot-logo-stage.json')
assert logo['boot_id'] == boot and logo['handoff_result'] == 'live panel retained for native DRM adoption'
assert (logo['magic'], logo['version'], logo['stage'], logo['error']) == (0xa523b001, 1, 0x100, 0)
assert logo['ovl_address'] == 0x42400000 and logo['pixel_count'] == 1024000
assert logo['de_version'] == 0x03500200 and logo['rcq_status'] & 4
assert logo['line_before'] != logo['line_after']
logs = load(state/'boot-console-log.json')
assert logs['boot_id'] == boot and logs['result'] == 'PASS'
assert logs['source'] == '/dev/kmsg' and logs['records'] > 100
assert logs['physical_frames'] > 0 and logs['native_takeover'] is True
profile = load('/usr/local/lib/tzx-boot-compact-v2/bundle-manifest.json')
receipt = json.loads(run('python3', '/home/debian/inspect_boot_console.py'))
assert receipt['boot_id'] == boot
speed = receipt['speed_receipt']
assert speed[:4] == [0xa523b501, 1, 0, 1] and speed[7] == 0
assert 0 < receipt['rail_started_ticks'] <= speed[4] < speed[5] < speed[6]
assert speed[6] - receipt['rail_started_ticks'] >= 24000000
assert receipt['panel']['panel_id'] == '0x936504'
assert speed[6]/24000000 < receipt['panel']['lit_counter_s'] < receipt['logo']['lit_counter_s']
cpu = receipt['cpu_receipt']
assert cpu[:4] == [0xa523cf01, 1, 4, 0] and cpu[8:10] == [1416000, 1150]
assert cpu[4:7] == cpu[10:13] and cpu[13] == 0 and cpu[14] == 0x54000 and cpu[17] > cpu[16]
assert receipt['trained_parameters'][:2] == [936, 7] and receipt['trained_parameters'][7] == 0x10007000
p = receipt['profile_receipt']
assert p[:2] == [0xa523f101, 1] and p[7] == p[8] == profile['new_read_bytes']//512 + 1
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x2d000) as view:
        packed = struct.unpack_from('<3Ii4I4Q2IQ', view, 0x800)
    assert packed[:4] == (0xa523c701, 1, 4, 0)
    assert packed[4] == profile['kernel_decoded_bytes']
    assert packed[5] + 32 == profile['items'][0]['bytes']
    assert packed[6] == packed[14] == 0 and packed[7] == profile['native_kernel_output_CRC32']
    assert packed[12:14] == (24000000, 3)
    assert 0 < packed[8] < packed[9] < packed[10] < packed[11]
    domains = {}
    for name, address in (('VO0', 0x07063000), ('VO1', 0x07064000), ('DE', 0x07065000)):
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=address) as view:
            domains[name] = struct.unpack_from('<I', view, 8)[0] & 15
    assert list(domains.values()) == [8, 8, 8]
finally:
    os.close(fd)
assert sha(Path('/boot/Image').read_bytes()) == profile['kernel_decoded_sha256']
health = load(state/'screen-boot-health.json')
assert health['boot_id'] == boot and health['result'] == 'PASS' and health['module_sha256'] == module
assert 'current 1280 x 800' in health['xrandr'] and ' right ' in health['xrandr']
assert health['display_setup']['fbcon_rotate'] == '1'
assert '0.000000, 1.000000, 0.000000, -1.000000, 0.000000, 1.000000' in health['display_setup']['touch_properties']
standby = load(state/'screen-standby-test.json')
assert standby['boot_id'] == boot and standby['result'] == 'PASS' and len(standby['samples']) == 5
units = ('tzx-display', 'tzx-touch', 'tzx-gpu', 'tzx-cpu-dvfs', 'tzx-gpu-performance',
         'tzx-emmc-hs', 'tzx-screen-health', 'tzx-dram-gpu-health', 'tzx-video',
         'tzx-zram', 'tzx-wifi', 'tzx-bluetooth', 'tzx-audio', 'lightdm',
         'tzx-gpu-api-health', 'tzx-pmic-poweroff')
assert run('systemctl', 'is-active', *units).split() == ['active']*len(units)
assert not run('systemctl', '--failed', '--no-legend', '--plain').strip()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
errors = Path('/sys/kernel/debug/mmc0/err_stats').read_text()
assert all(int(line.rsplit(':', 1)[1]) == 0 for line in errors.splitlines())
assert not [line for line in run('dmesg').splitlines() if re.search(
    r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error', line, re.I)]
print(run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'), end='', flush=True)
print(run('python3', '/usr/local/lib/tzx-pmic-poweroff/runtime.py', 'verify'), end='', flush=True)
mode = load('/run/tzx-performance-mode.json')
assert mode['boot_id'] == boot and mode['state'] == 'active' and mode['governors'] == ['performance', 'performance']
runtime = {name: load('/run/tzx-'+name+'.json') for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs')}
assert all(item['boot_id'] == boot and item['state'] == 'active' for item in runtime.values())
assert runtime['cpu-dvfs']['maximum_khz'] == [1416000, 1800000]
assert runtime['gpu-performance']['maximum_mhz'] == 600 and runtime['emmc-hs']['actual_hz'] == 100000000
mixed = load(state/'cpu-gpu-integration-qualified.json')
assert mixed['boot_id'] == boot and mixed['status'] == 'PASS'
desktop = load('/run/tzx-boot-streamline-desktop.json')
assert desktop['boot_id'] == boot and desktop['status'] == 'PASS'
assert set(desktop['desktop_processes']) == {'Xorg', 'xfce4-session', 'xfwm4', 'xfce4-panel', 'xfdesktop'}
timings = {}
for name in ('tzx-boot-console-log', 'tzx-boot-panel-handoff', 'tzx-display', 'lightdm'):
    item = dict(line.split('=', 1) for line in run('systemctl', 'show', name, '-p', 'Result',
        '-p', 'ExecMainStartTimestampMonotonic', '-p', 'ActiveEnterTimestampMonotonic').splitlines())
    assert item['Result'] == 'success'
    timings[name] = {key: int(value)/1e6 for key, value in item.items() if key.endswith('Monotonic')}
assert timings['tzx-boot-console-log']['ActiveEnterTimestampMonotonic'] <= timings['tzx-boot-panel-handoff']['ExecMainStartTimestampMonotonic']
assert boot == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof = dict(status='PASS', profile='screen-boot-console-1', boot_id=boot, captured_unix=int(time.time()),
    module_sha256=module, installed_files_verified=True, parent_raw_and_files_verified=True,
    native_parameters=values, live_power_domains=domains, log=logs, adoption=adoption,
    compact_receipt=list(packed), boot_receipts=receipt, screen_health=health,
    standby=standby, mixed_load=mixed, performance_mode=mode, runtime_statuses=runtime,
    desktop=desktop, service_timings=timings, failed_services=[],
    physical_power_key_test=False,
    owner_confirmation='Live boot logs visible; no color bars or intermediate black screen; landscape desktop and touch normal',
    scope='Original tablet only; first SRAM artwork unchanged; userspace /dev/kmsg then native VT1 then desktop',
    limitation='Display domains kept powered; system suspend and this child physical key-on not qualified')
atomic(state/('boot-console-qualified-'+boot+'.json'), proof)
atomic(state/'boot-console-qualified.json', proof)
# Update only this child's qualification fields. Historical parent receipts and
# their immutable SHA pins are preserved exactly, including earlier failures.
for name in ('screen-installed.json', 'screen-qualified.json'):
    item = load(state/name)
    assert item['startup_child'] == 'screen-boot-console-1'
    if name == 'screen-qualified.json':
        assert item['module_sha256'] == module
    item.update(startup_child_qualification='PASS', startup_child_qualified_boot_id=boot,
                startup_child_proof='/var/lib/tzx/boot-console-qualified.json')
    atomic(state/name, item)
installed['qualification'] = dict(status='PASS', boot_id=boot, proof='/var/lib/tzx/boot-console-qualified.json')
atomic(state/'screen-boot-console-installed.json', installed)
print('BOOT_CONSOLE_LIVE_LOG_CONTINUOUS_HANDOFF_AND_FULL_STACK_PASS', json.dumps(dict(
    boot_id=boot, log_records=logs['records'], log_frames=logs['physical_frames'],
    last_desktop_process_kernel_s=desktop['last_desktop_process_start_kernel_s'],
    mixed_load_s=mixed['seconds'], failed_services=[])), flush=True)
