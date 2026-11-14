"""Capture the verified #5 CPUfreq addition and #4 boot rollback, without rootfs."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import time

parser = argparse.ArgumentParser()
parser.add_argument('--name', default='cpufreq-checkpoint')
args = parser.parse_args()
assert args.name.startswith('cpufreq-') and all(c.isalnum() or c == '-' for c in args.name)
assert os.geteuid() == 0 and '#5 ' in os.uname().version
cid = Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()
assert cid == '3e01ff55454d20202010209170281b59'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
record_path = Path('/var/lib/tzx/cpufreq-runtime-installed.json')
record = json.loads(record_path.read_text())
assert record['state'] == 'manual_schedutil_service_stop_start_and_autostart_boot_verified'
assert record['verified_boot_id'] == boot and not Path('/sys/module/panfrost').exists()
paths = [Path('/') / name for name in record['files']]
paths += [record_path, Path('/var/lib/tzx/cpufreq-framework-installed.json'),
          Path('/home/debian/cpufreq-framework-bundle.bin'),
          Path('/home/debian/cpufreq-framework-bundle.json'),
          Path('/home/debian/cpufreq-divider-trial.json'), Path('/home/debian/cpufreq-schedutil-trial.json'),
          Path('/boot/config-7.3.3-tzx-a523-accel1'),
          Path('/root/tzx-recovery/cpufreq-framework/bundle-before-cpufreq-framework.bin'),
          Path('/root/tzx-recovery/cpufreq-framework/config-before-cpufreq-framework'),
          Path('/home/debian/install_cpufreq_framework_candidate.py'),
          Path('/home/debian/rollback_cpufreq_runtime.py')]
paths += [Path('/root/tzx-recovery/cpufreq-runtime') / name
          for name in ('before.json', 'installed.json', 'rollback.py')]
if 'startup_taint_fix' in record:
    paths += [Path('/home/debian/fix_cpufreq_startup_taint.py')]
    paths += [Path('/root/tzx-recovery/cpufreq-runtime/startup-taint-fix') / name
              for name in ('runtime-before.py', 'installed-before.json', 'state-before.json')]
contents = {}
for path in paths:
    assert path.is_file() and not path.is_symlink()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if str(path).lstrip('/') in record['files']:
        assert digest == record['files'][str(path).lstrip('/')]
    contents[str(path).lstrip('/')] = data
new = contents['home/debian/cpufreq-framework-bundle.bin']
assert hashlib.sha256(new).hexdigest() == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
with open('/dev/mmcblk0', 'rb', buffering=0) as disk:
    assert os.pread(disk.fileno(), len(new), 65536 * 512) == new
    contents['raw/active-header-lba4096.bin'] = os.pread(disk.fileno(), 512, 4096 * 512)
assert contents['raw/active-header-lba4096.bin'] == new[:512]
manifest = dict(cid=cid, boot_id=boot, kernel=os.uname().version,
                scope='verified CPUfreq addition, split-slot #5 bundle and #4 boot rollback; no rootfs or credentials',
                files={name: hashlib.sha256(data).hexdigest() for name, data in contents.items()})
contents['MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
destination = Path('/home/debian') / (args.name + '.tar.gz')
with destination.open('xb') as output:
    with tarfile.open(fileobj=output, mode='w:gz', compresslevel=3) as archive:
        for name, data in sorted(contents.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
            archive.addfile(info, io.BytesIO(data))
    output.flush()
    os.fsync(output.fileno())
destination.chmod(0o644)
print('CPUFREQ_CHECKPOINT_CREATED', json.dumps(dict(path=str(destination),
      bytes=destination.stat().st_size, sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
      files=len(manifest['files']), boot_id=boot)), flush=True)
