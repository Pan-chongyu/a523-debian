"""Update only the CPUfreq wrapper's early-boot taint guard, retaining rollback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) in (0, 4096)
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert not Path('/run/tzx-cpufreq-runtime.json').exists()
base = Path('/root/tzx-recovery/cpufreq-runtime')
record_path = Path('/var/lib/tzx/cpufreq-runtime-installed.json')
record = json.loads(record_path.read_text())
installed = json.loads((base / 'installed.json').read_text())
expected = {
    'usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko': '95a0d572d6a363b1b70984cf51e2ae6dff7e8470fc3a2e66072af5a8a508903c',
    'usr/local/lib/tzx-cpufreq/runtime.py': '296f5f8ce729765b1d297d918a1d59ab405825c9a0dc0658898921074a071299',
    'etc/systemd/system/tzx-cpufreq.service': 'd08bde73706e602423233dfa4216f9b1770fc7b605b93404d516968c19534aac',
}
assert installed == record['files'] == expected
for name, digest in expected.items():
    target = Path('/') / name
    assert not target.is_symlink() and hashlib.sha256(target.read_bytes()).hexdigest() == digest
name = 'usr/local/lib/tzx-cpufreq/runtime.py'
target = Path('/') / name
candidate = Path('/home/debian/tzx_cpufreq_runtime-startup-v2.py').read_bytes()
new_sha = '65cd54a0a70790712dfb7ee714721530b00e7a4c275050d1a355c961004c604c'
assert hashlib.sha256(candidate).hexdigest() == new_sha
compile(candidate, str(target), 'exec')
backup = base / 'startup-taint-fix'
backup.mkdir(mode=0o700, exist_ok=False)
(backup / 'runtime-before.py').write_bytes(target.read_bytes())
(backup / 'installed-before.json').write_bytes((base / 'installed.json').read_bytes())
(backup / 'state-before.json').write_bytes(record_path.read_bytes())
os.sync()


def replace(path, data):
    temporary = path.with_name(path.name + '.startup-fix-new')
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o644)
    temporary.replace(path)


replace(target, candidate)
installed[name] = new_sha
record['files'] = installed
record['state'] = 'startup_taint_guard_fixed_boot_verification_pending'
record['startup_taint_fix'] = {
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'time_unix': int(time.time()), 'old_sha256': expected[name], 'new_sha256': new_sha,
    'reason': 'clean kernel taint=0 is valid before the first external module',
    'driver_or_frequencies_changed': False,
}
replace(base / 'installed.json', (json.dumps(installed, indent=2) + '\n').encode())
replace(record_path, (json.dumps(record, indent=2) + '\n').encode())
os.sync()
subprocess.run(['systemctl', 'reset-failed', 'tzx-cpufreq.service'], check=True)
for operation in ('start', 'stop', 'start'):
    subprocess.run(['systemctl', operation, 'tzx-cpufreq.service'], check=True, timeout=50)
    print('CPUFREQ_STARTUP_FIX_SERVICE_' + operation.upper() + '_PASS', flush=True)
assert subprocess.check_output(['systemctl', 'is-active', 'tzx-cpufreq.service'], text=True).strip() == 'active'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert hashlib.sha256(target.read_bytes()).hexdigest() == new_sha
print('CPUFREQ_STARTUP_TAINT_GUARD_PATCHED_RUNTIME_CYCLE_PASS', new_sha, flush=True)
