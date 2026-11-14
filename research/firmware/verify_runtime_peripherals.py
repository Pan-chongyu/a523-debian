"""Check installed runtime modules, startup services, and the raw boot image."""
import hashlib
import json
from pathlib import Path
import subprocess

def command(*args):
    return subprocess.check_output(args, text=True).strip()

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert command('uname', '-r') == '7.3.3-tzx-a523'
manifest = json.loads(Path('/home/debian/runtime-install-stage/FILES.json').read_text())
for name, digest in manifest.items():
    assert '..' not in Path(name).parts and not Path(name).is_absolute()
    assert hashlib.sha256((Path('/') / name).read_bytes()).hexdigest() == digest, name
for unit in ('tzx-touch.service', 'tzx-wifi.service', 'ssh.service'):
    assert command('systemctl', 'is-active', unit) == 'active', unit
for unit in ('tzx-touch.service', 'tzx-wifi.service'):
    assert command('systemctl', 'is-enabled', unit) == 'enabled', unit
assert command('systemctl', 'is-system-running') == 'running'
assert command('findmnt', '-n', '-o', 'SOURCE', '--target', '/') == '/dev/mmcblk0p2'
assert command('findmnt', '-n', '-o', 'SOURCE', '--target', '/boot') == '/dev/mmcblk0p1'
assert Path('/sys/class/net/wlan0/address').read_text().strip() == '02:cf:db:e2:24:c8'
assert Path('/sys/kernel/debug/mmc1/clock').read_text().strip() == '12000000'
assert Path('/sys/bus/sdio/devices/mmc1:390b:1/device').read_text().strip() == '0x0082'
assert Path('/sys/bus/i2c/devices/1-0040/driver').resolve().name == 'tzx-gsl3670'
assert Path('/sys/module/aic8800_fdrv/parameters/ps_on').read_text().strip() == 'N'
assert Path('/sys/module/aic8800_fdrv/parameters/aicwf_dbg_level').read_text().strip() == '1'
with open('/dev/mmcblk0', 'rb', buffering=0) as disk:
    disk.seek(256 * 512)
    loader_sha = hashlib.sha256(disk.read(40960)).hexdigest()
    disk.seek(4096 * 512)
    bundle_sha = hashlib.sha256(disk.read(13809664)).hexdigest()
assert loader_sha == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
assert bundle_sha == 'caca235b95ffab9bdda0769c1112bf6f201b3853805a705c677526d0d982f5cb'
log = command('dmesg')
unexpected = [line for line in log.splitlines() if any(word in line for word in
              ('WARNING:', 'BUG:', 'Oops:', 'Call trace:', 'refcount_t:'))]
assert not unexpected, unexpected
print(json.dumps({
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'kernel': command('uname', '-a'), 'verified_installed_files': len(manifest),
    'touch_service': 'enabled, active', 'wifi_service': 'enabled, active',
    'touch_stats': Path('/sys/bus/i2c/devices/1-0040/stats').read_text().strip(),
    'wifi_mac': Path('/sys/class/net/wlan0/address').read_text().strip(),
    'sdio_ios': Path('/sys/kernel/debug/mmc1/ios').read_text().strip(),
    'sdio_errors': Path('/sys/kernel/debug/mmc1/err_stats').read_text().strip(),
    'system_state': 'running', 'kernel_warnings': unexpected,
    'loader_sha256': loader_sha, 'bundle_sha256': bundle_sha,
}, indent=2))
