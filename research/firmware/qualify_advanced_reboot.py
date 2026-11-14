"""Record the actual normal reboot of the installed advanced profile."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

assert os.geteuid() == 0
STATE = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
previous = '9134ee19-332d-4aab-a504-7269d4fe19cb'
assert boot != previous
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert '#5 ' in os.uname().version
sha = lambda data: hashlib.sha256(data).hexdigest()

def run(*args, timeout=60):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)

proof = json.loads((STATE/'advanced-performance-qualified.json').read_text())
assert proof['status'] == 'PASS' and proof['boot_id'] == boot
assert proof['cpu_peak_khz'] == [1416000, 1488000]
assert proof['video_hardware_irq_delta'] >= 600 and proof['iommu_faults'] == 0
assert proof['emmc_hz'] == 100000000 and proof['emmc_timing'] == 'HS200'
assert proof['zram_bytes'] == 2147483648

units = ('tzx-cpu-dvfs', 'tzx-gpu-performance', 'tzx-video', 'tzx-zram', 'tzx-emmc-hs')
assert run('systemctl', 'is-active', *units).split() == ['active']*len(units)
assert run('systemctl', 'is-enabled', *units).split() == ['enabled']*len(units)
run('systemctl', 'is-active', '--quiet', 'tzx-wifi', 'tzx-bluetooth', 'tzx-audio')
assert not run('systemctl', '--failed', '--no-legend', '--plain').strip()
health = {}
for name, key in (('screen-boot-health', 'result'), ('dram-gpu-boot-health', 'status')):
    data = json.loads((STATE/(name+'.json')).read_text())
    assert data['boot_id'] == boot and data[key] == 'PASS'
    health[name] = data
screen = health['screen-boot-health']
assert 'current 1280 x 800' in screen['xrandr'] and ' right ' in screen['xrandr']
assert screen['display_setup']['fbcon_rotate'] == '1'
assert '0.000000, 1.000000, 0.000000, -1.000000, 0.000000, 1.000000' in screen['display_setup']['touch_properties']
assert Path('/sys/class/graphics/fbcon/rotate').read_text().strip() == '1'

manifests = {}
for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs'):
    data = json.loads((Path('/usr/local/lib')/('tzx-'+name)/'manifest.json').read_text())
    for path, digest in data['files'].items():
        assert sha(Path(path).read_bytes()) == digest, path
    manifests[name] = data
video = json.loads((STATE/'video-installed.json').read_text())
for path, digest in video['files'].items():
    assert sha(Path(path).read_bytes()) == digest, path
manifests['video'] = video['files']
native = json.loads(Path('/usr/local/lib/tzx-zram/native-installed.json').read_text())
for path, digest in native.items():
    assert sha(Path(path).read_bytes()) == digest, path
manifests['zram_native'] = native
assert sha(Path('/opt/tzx-video/usr/lib/aarch64-linux-gnu/libcdc_base.so').read_bytes()) == '2200a553e9cb6d7a26b245e92e9609b72894fe54679554c93940aae7fe6ffb19'
assert not Path('/sys/module/tzx_video_heap').exists(), 'Experimental heap must not autoload'

statuses = {}
for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs'):
    data = json.loads(Path('/run/tzx-'+name+'.json').read_text())
    assert data['boot_id'] == boot and data['state'] == 'active'
    assert json.loads((STATE/(name+'-pending.json')).read_text())['boot_id'] == boot
    statuses[name] = data
zram = json.loads(run('python3', '/usr/local/lib/tzx-zram/runtime.py', 'status'))
assert zram['boot_id'] == boot and zram['active'] and zram['ram_only']
assert zram['logical_bytes'] == 2147483648 and '[lz4]' in zram['algorithm']
assert zram['swappiness'] == '100' and zram['page_cluster'] == '0'
assert '/dev/zram0' in zram['swaps'] and zram['swaps'].splitlines()[1].split()[4] == '100'
statuses['zram'] = zram
assert statuses['cpu-dvfs']['maximum_khz'] == [1416000, 1488000]
assert statuses['emmc-hs']['actual_hz'] == 100000000 and not statuses['emmc-hs']['hs400_enabled']
errors = Path('/sys/kernel/debug/mmc0/err_stats').read_text()
assert all(int(row.rsplit(':', 1)[1]) == 0 for row in errors.splitlines())
assert 'actual clock:\t22222222 Hz' in Path('/sys/kernel/debug/mmc1/ios').read_text()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
bad = [line for line in run('dmesg').splitlines() if re.search(
    r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error|Aborting journal', line, re.I)]
assert not bad, bad
assert any(' / ' in row and ' rw,' in row for row in Path('/proc/mounts').read_text().splitlines())
for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs'):
    path = STATE/(name+'-failure.json')
    if path.exists():
        assert json.loads(path.read_text())['boot_id'] != boot

run('python3', '/home/debian/install_hs_kernel.py', 'verify-boot')
assert sha(gzip.decompress(Path('/proc/config.gz').read_bytes())) == '59cc725631e95f3726080322e19f4868ef461035e85d6f7dd02b5be2915aced6'
assert sha(Path('/boot/Image').read_bytes()) == '4c47d5cf91a544b0c9d47901309b0bca8e8ff71320f91a4088da37ab565615fc'
with Path('/dev/mmcblk0').open('rb', buffering=0) as disk:
    identities = {}
    for name, lba, length, expected in (
        ('trained_TOC0', 256, 40960, '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'),
        ('active_header', 4096, 512, '47e503b504a0b4260a3509fccad1918408058ffe47a8cbb9e9b84f7abed91d1f'),
        ('recovery_extended_slot', 65536, 15008768, '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'),
        ('active_HS_v4_slot', 98304, 15008768, '2792b0e8b1087287c4e1da8f036fb3a72b11d4b5e21da7e38111d90785a6509e')):
        disk.seek(lba*512)
        identities[name] = sha(disk.read(length))
        assert identities[name] == expected, name

player_file = Path('/home/debian/video-player-result.json')
assert player_file.stat().st_mtime > time.time()-float(Path('/proc/uptime').read_text().split()[0])
player = json.loads(player_file.read_text())
assert player['hardware_decoders'] == ['omxh264dec'] and player['eos'] and not player['errors']
assert player['visible_dimensions'] == [1920, 1080]
assert run('systemctl', 'show', 'tzx-video-reboot-observe', '-p', 'ExecMainStatus', '--value').strip() == '0'

idle = []
for unused in range(30):
    idle.append({'cpu_khz': [int(Path('/sys/devices/system/cpu/cpufreq/policy'+str(n)+'/scaling_cur_freq').read_text()) for n in (0, 4)],
                 'gpu_runtime': Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip()})
    time.sleep(.4)
assert [min(s['cpu_khz'][n] for s in idle) for n in (0, 1)] == [120000, 120000]
assert any(s['gpu_runtime'] == 'suspended' for s in idle)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
record = dict(status='PASS', previous_boot_id=previous, boot_id=boot,
    normal_reboot_verified=True, poweroff_key_on_verified=False, units=list(units),
    combined_load=proof, installed_manifests=manifests, runtime_statuses=statuses,
    boot_health=health, early_boot_hashes=identities, failed_units=[], emmc_errors=errors,
    idle_cpu_minimum_khz=[120000, 120000], gpu_autosuspend=True, idle_samples=idle,
    player_after_reboot=player, experimental_heap_absent=True,
    limits=['HS400 and HS200 above 100MHz are not qualified',
            'Full 1080p60 desktop presentation still drops frames; decoder throughput is a separate measurement',
            'Browser hardware decoding is not integrated',
            'Current combination has not been tested by poweroff and physical key-on'])
target = STATE/'advanced-performance-reboot-qualified.json'
assert not target.exists()
target.write_text(json.dumps(record, indent=2)+'\n')
for name in ('cpu-dvfs-qualified', 'cpu-dvfs-installed', 'emmc-hs-qualified',
             'emmc-hs-installed', 'video-qualified', 'video-installed', 'zram-qualified'):
    path = STATE/(name+'.json')
    data = json.loads(path.read_text())
    data.update(normal_reboot_verified=True, normal_reboot_id=boot, poweroff_key_on_verified=False,
                normal_reboot_proof_sha256=sha(target.read_bytes()))
    if name == 'cpu-dvfs-qualified':
        data['scope'] = 'Voltage-aware DVFS qualified online and across a real normal reboot'
    temporary = path.with_suffix('.json.reboot-new')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    temporary.replace(path)
os.sync()
print('ADVANCED_PROFILE_NORMAL_REBOOT_AND_COEXISTENCE_PASS', json.dumps({
    'boot_id': boot, 'CPU_khz': [1416000, 1488000], 'eMMC_hz': 100000000,
    'zram_bytes': 2147483648, 'idle_cpu_minimum_khz': [120000, 120000],
    'gpu_autosuspend': True, 'screen_orientation': 'right 1280x800',
    'normal_reboot_verified': True, 'poweroff_key_on_verified': False}), flush=True)
