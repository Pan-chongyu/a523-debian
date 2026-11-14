"""Install the divider service only after same-boot manual and governor proof."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert not Path('/sys/module/panfrost').exists()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
manual = json.loads(Path('/home/debian/cpufreq-divider-trial.json').read_text())
governor = json.loads(Path('/home/debian/cpufreq-schedutil-trial.json').read_text())
for proof in (manual, governor):
    assert proof['result'] == 'PASS' and proof['boot_id'] == boot and len(proof['cycles']) == 2
assert governor['module_sha256'] == '95a0d572d6a363b1b70984cf51e2ae6dff7e8470fc3a2e66072af5a8a508903c'
assert governor['memory_2560MiB'] == governor['file_integrity'] == 'PASS'
journals = {}
for unit, marker in (
    ('tzx-cpufreq-divider-v2-trial.service', 'CPUFREQ_TWO_LOADS_INDEPENDENT_CLUSTERS_ACTUAL_SPEED_RAM_AND_UNLOAD_PASS'),
    ('tzx-cpufreq-schedutil-trial.service', 'CPUFREQ_SCHEDUTIL_BOTH_CLUSTERS_RAM_AND_FILES_PASS')):
    properties = subprocess.check_output(['systemctl', 'show', unit, '-p', 'Result',
                                         '-p', 'ExecMainStatus', '-p', 'ActiveState'], text=True)
    assert all(text in properties for text in ('Result=success\n', 'ExecMainStatus=0\n', 'ActiveState=inactive\n'))
    journal = subprocess.check_output(['journalctl', '-b', '0', '-u', unit, '--no-pager'], text=True)
    assert marker in journal and 'CPUFREQ_DIVIDER_UNLOADED_EXACT_BASELINE_RESTORED' in journal
    journals[unit] = hashlib.sha256(journal.encode()).hexdigest()
stage = Path('/home/debian/cpufreq-runtime-stage')
files = json.loads((stage / 'FILES.json').read_text())
assert set(files) == {'usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko',
                      'usr/local/lib/tzx-cpufreq/runtime.py', 'etc/systemd/system/tzx-cpufreq.service'}
assert files['usr/local/lib/tzx-cpufreq/tzx_cpufreq_divider.ko'] == governor['module_sha256']
for name, digest in files.items():
    assert hashlib.sha256((stage / name).read_bytes()).hexdigest() == digest
backup = Path('/root/tzx-recovery/cpufreq-runtime')
backup.mkdir(parents=True, exist_ok=False)
previous = {}
for name in files:
    target = Path('/') / name
    assert not target.is_symlink()
    if target.exists():
        saved = backup / 'files' / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(target.read_bytes())
        previous[name] = {'sha256': hashlib.sha256(saved.read_bytes()).hexdigest(),
                          'mode': target.stat().st_mode & 0o777}
    else:
        previous[name] = None
(backup / 'before.json').write_text(json.dumps(previous, indent=2) + '\n')
(backup / 'installed.json').write_text(json.dumps(files, indent=2) + '\n')
(backup / 'rollback.py').write_bytes(Path('/home/debian/rollback_cpufreq_runtime.py').read_bytes())
for name, digest in files.items():
    target = Path('/') / name
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.cpufreq-new')
    temporary.write_bytes((stage / name).read_bytes())
    temporary.chmod(0o644)
    temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemd-analyze', '--man=no', 'verify', 'tzx-cpufreq.service'], check=True)
subprocess.run(['systemctl', 'enable', 'tzx-cpufreq.service'], check=True)
record = {'state': 'manual_and_schedutil_trials_passed_service_test_pending', 'boot_id': boot,
          'files': files, 'proof_journal_sha256': journals, 'maximum_kHz': 480000,
          'PLL_DSU_voltage_changed': False}
Path('/var/lib/tzx/cpufreq-runtime-installed.json').write_text(json.dumps(record, indent=2) + '\n')
os.sync()
print('CPUFREQ_RUNTIME_INSTALLED_SAME_BOOT_PROOF_VERIFIED', json.dumps(record), flush=True)
