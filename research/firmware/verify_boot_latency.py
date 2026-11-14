"""Check actual boot ordering, the unchanged accelerated stack and timing."""
import gzip
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import subprocess
import sys
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
state = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert sys.argv[1:] in ([],['--key-on'])
boot_kind='PMIC-key-on' if sys.argv[1:]==['--key-on'] else 'normal-reboot'
order = json.loads((state/'boot-latency-installed.json').read_text())
early_cpub = (state/'boot-early-cpub-installed.json').exists()
sha = lambda b: hashlib.sha256(b).hexdigest()
with open('/dev/mmcblk0','rb',buffering=0) as device:
    device.seek(256*512)
    actual_toc0_sha256 = sha(device.read(40960))
variants=('boot-hwcrc','boot-icache','boot-fast','boot-profile','boot-wide','boot-early-cpub','boot-crc')
matches=[]
for variant in variants:
    path=state/(variant+'-installed.json')
    if path.exists():
        value=json.loads(path.read_text())
        if value['toc0_sha256']==actual_toc0_sha256 and 'restored' not in value['state']:
            matches.append((variant,path))
assert len(matches)==1,matches
variant,loader_state=matches[0]
wide = variant in ('boot-wide','boot-fast','boot-icache','boot-hwcrc')
profiled = variant in ('boot-profile','boot-fast','boot-icache','boot-hwcrc')
crc = json.loads(loader_state.read_text())
assert boot != order['installed_boot_id'] and boot != crc['installed_boot_id']


def run(*args, timeout=60):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)


units = ('tzx-cpub', 'tzx-touch', 'tzx-display', 'tzx-gpu', 'lightdm', 'tzx-screen-health',
         'tzx-dram-gpu-health', 'tzx-cpu-dvfs', 'tzx-gpu-performance', 'tzx-emmc-hs',
         'tzx-zram', 'tzx-video', 'tzx-wifi', 'tzx-bluetooth', 'tzx-audio', 'tzx-pmic-poweroff')
for attempt in range(100):
    values = subprocess.run(['systemctl', 'is-active', *units], text=True, capture_output=True, timeout=15)
    ready = values.stdout.split() == ['active']*len(units)
    for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs'):
        path = Path('/run/tzx-'+name+'.json')
        ready = ready and path.exists() and json.loads(path.read_text()).get('state') == 'active'
    if ready:
        break
    time.sleep(.5)
else:
    raise RuntimeError('Installed services did not settle: '+values.stdout)

assert not run('systemctl', '--failed', '--plain', '--no-legend').strip()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert sha(Path('/boot/Image').read_bytes()) == '470dd0c350c7ef7aad392eac3a35237672862f0fffdacea8da4e6adb6740e6e4'
assert sha(gzip.decompress(Path('/proc/config.gz').read_bytes())) == '8228e905b2ae482d57f071c901a63888497b93de969049659151d6abeb1cff97'
for name, item in order['files'].items():
    assert sha(Path(name).read_bytes()) == item['installed_sha256'], name
for component in ('tzx-cpu-full', 'tzx-gpu-devfreq', 'tzx-emmc-hs'):
    manifest = json.loads((Path('/usr/local/lib')/component/'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        assert sha(Path(name).read_bytes()) == digest, name
installer={'boot-hwcrc':'install_boot_hwcrc.py','boot-icache':'install_boot_icache.py','boot-fast':'install_boot_fast.py','boot-profile':'install_boot_profile.py',
           'boot-wide':'install_boot_wide.py','boot-early-cpub':'install_boot_cpub.py','boot-crc':'install_boot_crc.py'}
print(run('python3', '/home/debian/'+installer[variant],
          'verify', crc['toc0_sha256']), end='', flush=True)
receipt = None
wide_receipt = None
if early_cpub:
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x2d000) as view:
            import struct
            receipt = list(struct.unpack_from('<6I', view, 0xf40))
            if wide:
                wide_receipt = list(struct.unpack_from('<8I', view, 0xf80))
    finally:
        os.close(fd)
    assert receipt[:4] in ([0xa523cb01, 1, 0x48801400, 0],
                          [0xa523cb01, 2, 0xc8801400, 3 << 24])
    assert receipt[5] == 3 << 24
    print('EARLY_CPUB_480MHz_SRAM_RECEIPT_PASS', [hex(v) for v in receipt], flush=True)
    if wide:
        assert wide_receipt[:7] == [0xa523b801, 1, 0, 0x10000, 3, 2, 0], wide_receipt
        print('WIDE_BOOT_THREE_DISTINCT_SECTORS_AND_8BIT_RECEIPT_PASS',
              [hex(v) for v in wide_receipt], flush=True)
print(run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'), end='', flush=True)
print(run('python3', '/usr/local/lib/tzx-pmic-poweroff/runtime.py', 'verify'), end='', flush=True)

props = {}
for name in ('tzx-cpub', 'systemd-udevd', 'systemd-udev-trigger', 'tzx-touch', 'tzx-display',
             'tzx-wifi', 'tzx-gpu', 'lightdm', 'tzx-screen-health', 'graphical.target'):
    output = run('systemctl', 'show', name, '-p', 'Id', '-p', 'After', '-p', 'Before',
                 '-p', 'ExecMainStartTimestampMonotonic', '-p', 'ActiveEnterTimestampMonotonic')
    props[name] = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
at = lambda unit, prop: int(props[unit][prop]) / 1000000
assert at('tzx-cpub', 'ActiveEnterTimestampMonotonic') <= at('systemd-udevd', 'ExecMainStartTimestampMonotonic')
assert at('tzx-cpub', 'ActiveEnterTimestampMonotonic') <= at('systemd-udev-trigger', 'ExecMainStartTimestampMonotonic')
assert at('tzx-touch', 'ActiveEnterTimestampMonotonic') <= at('tzx-display', 'ExecMainStartTimestampMonotonic')
assert 'tzx-wifi.service' not in props['tzx-display']['After'].split()

health = json.loads((state/'screen-boot-health.json').read_text())
assert health['boot_id'] == boot and health['result'] == 'PASS'
assert 'current 1280 x 800' in health['xrandr'] and ' right ' in health['xrandr']
assert health['display_setup']['fbcon_rotate'] == '1'
assert '0.000000, 1.000000, 0.000000, -1.000000, 0.000000, 1.000000' in health['display_setup']['touch_properties']
assert Path('/sys/class/backlight/tzx-panel/actual_brightness').read_text().strip() == Path('/sys/class/backlight/tzx-panel/brightness').read_text().strip()
for name in ('screen_buffer_errors', 'screen_panel_errors'):
    assert int((Path('/sys/module/tzx_display/parameters')/name).read_text()) == 0
assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() == 'Y'
runtime = {name: json.loads(Path('/run/tzx-'+name+'.json').read_text())
           for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs')}
assert all(v['boot_id'] == boot and v['state'] == 'active' for v in runtime.values())
assert runtime['cpu-dvfs']['maximum_khz'] == [1416000, 1800000]
assert runtime['cpu-dvfs']['capacity'] == [725]*4+[1024]*4
assert runtime['gpu-performance']['clock_owner'] == 'Panfrost devfreq'
assert runtime['gpu-performance']['maximum_mhz'] == 600
assert runtime['emmc-hs']['actual_hz'] == 100000000
compute = run('python3', '/home/debian/verify_gpu_compute.py', timeout=40)
assert 'MALI_G57_COMPUTE_ALL_WORDS_PASS' in compute
print(compute, end='', flush=True)
errors = Path('/sys/kernel/debug/mmc0/err_stats').read_text()
assert all(int(line.rsplit(':', 1)[1]) == 0 for line in errors.splitlines())
log = run('dmesg')
assert not [line for line in log.splitlines() if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error', line, re.I)]
assert 'ordering cycle' not in run('journalctl', '-b', '--no-pager').lower()
match = re.search(r'\[\s*([0-9.]+)\] Console: switching to colour frame buffer', log)
assert match
timing = dict(first_fbcon_kernel_s=float(match[1]),
    display_ready_kernel_s=at('tzx-display', 'ActiveEnterTimestampMonotonic'),
    lightdm_started_kernel_s=at('lightdm', 'ExecMainStartTimestampMonotonic'),
    lightdm_active_kernel_s=at('lightdm', 'ActiveEnterTimestampMonotonic'),
    screen_health_pass_kernel_s=at('tzx-screen-health', 'ActiveEnterTimestampMonotonic'))
baseline_display = int(order['baseline_units']['tzx-display']['ActiveEnterTimestampMonotonic'])/1000000
baseline_lightdm = int(order['baseline_units']['lightdm']['ExecMainStartTimestampMonotonic'])/1000000
record = dict(status='PASS', boot_id=boot, timing=timing,verification_method=boot_kind,
    baseline_before_order_changes=dict(display_ready_kernel_s=baseline_display, lightdm_started_kernel_s=baseline_lightdm),
    saved_display_kernel_s=round(baseline_display-timing['display_ready_kernel_s'], 3),
    saved_lightdm_kernel_s=round(baseline_lightdm-timing['lightdm_started_kernel_s'], 3),
    units=props, screen_health=health, runtime_statuses=runtime, GPU_compute=compute,
    systemd_time=run('systemd-analyze', 'time'), critical_chain=run('systemd-analyze', 'critical-chain'),
    toc0_sha256=crc['toc0_sha256'], raw_boot_invariants=crc['raw_invariants'],
    failed_units=[], MMC_errors=errors, visual_confirmation='pending',
    poweroff_key_on_for_fast_crc='pending', PMIC_and_DRAM_code_unchanged=True,
    early_CPUB_before_Linux=early_cpub, early_CPUB_receipt=receipt,
    boot_8bit_verified=wide, wide_boot_receipt=wide_receipt)
if profiled:
    record['boot_profile_readout']=run('python3','/home/debian/read_boot_profile.py')
if variant=='boot-hwcrc':
    fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
    try:
        with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x2d000) as mem:
            hw_crc=[struct.unpack_from('<I',mem,0xfc0+4*i)[0] for i in range(4)]
            profile_count=struct.unpack_from('<I',mem,0xc00+52)[0]
    finally:os.close(fd)
    assert hw_crc[0]==0xa523cc01 and (hw_crc[1]>>16)&15==1
    assert hw_crc[2]==1 and hw_crc[3]==profile_count==29314
    record['IEEE_hardware_CRC32_all_sectors_verified']=hw_crc
    print('IEEE_HARDWARE_CRC32_ALL_29314_SECTORS_PASS',[hex(v) for v in hw_crc],flush=True)
if variant=='boot-icache':
    fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
    try:
        with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x2d000) as mem:
            control=[struct.unpack_from('<I',mem,0xfc0+4*i)[0] for i in range(6)]
    finally:os.close(fd)
    assert control[0]==0xa5231c01 and control[1]==4 and not control[2]&0x1005
    assert control[3]==control[2]|4096 and control[4]==control[2] and control[5]==0x54000
    record['temporary_icache_exactly_restored']=control
    print('ICACHE_ONLY_AND_EXACT_HANDOFF_STATE_RESTORED_PASS',[hex(v) for v in control],flush=True)
clean_stop=state/'performance-clean-shutdown.json'
if clean_stop.exists():
    clean=json.loads(clean_stop.read_text())
    for name,digest in clean['files'].items():assert sha(Path(name).read_bytes())==digest,name
    assert sha((state/'cpu-full-qualified.json').read_bytes())==clean['restored_exact_CPU_qualification_sha256']
    for name in ('tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs'):
        assert run('systemctl','show',name,'-p','KillMode','--value').strip()=='mixed'
    assert boot!=clean['boot_id']
    clean.update(CPU_qualification_preserved=True,all_three_supervisors_automatically_active=True)
    if boot_kind=='normal-reboot':clean.update(normal_reboot_verification='PASS',verified_boot_id=boot)
    else:clean.update(poweroff_key_on_verification='PASS',poweroff_key_on_boot_id=boot)
    clean_stop.write_text(json.dumps(clean,indent=2)+'\n')
(state/'boot-latency-qualified.json').write_text(json.dumps(record, indent=2)+'\n')
order.update(state='actual-'+boot_kind+'-order-verified', verified_boot_id=boot, timing=timing)
(state/'boot-latency-installed.json').write_text(json.dumps(order, indent=2)+'\n')
crc.update(state='actual-'+boot_kind+'-verified', verified_boot_id=boot)
loader_state.write_text(json.dumps(crc, indent=2)+'\n')
os.sync()
print('BOOT_LATENCY_AND_UNCHANGED_NATIVE_STACK_PASS', json.dumps(dict(boot_id=boot,
    timing=timing, saved_display_kernel_s=record['saved_display_kernel_s'],
    saved_lightdm_kernel_s=record['saved_lightdm_kernel_s'], CPU_max_khz=[1416000,1800000],
    GPU_native_mhz=[150,200,300,400,600], HS200_hz=100000000)), flush=True)
