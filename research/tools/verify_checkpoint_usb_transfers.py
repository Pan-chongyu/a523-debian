"""Bounded default-rate transfers after a transient NCM disconnect."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
snapshot = json.loads((root/'build/dram-gpu-cooling-v2-installed-checkpoint.json').read_text())
expected = snapshot['archive_sha256']
records = []
report = root/'evidence/cpu-cooling-v2-usb-full-rate-recheck.json'
assert not report.exists()
for cycle in (1, 2):
    target = root/'build'/f'usb-checkpoint-transfer-{cycle}.tmp'
    assert not target.exists() and target.resolve().parent == (root/'build').resolve()
    started = time.monotonic()
    result = subprocess.run(['scp', '-q', '-i', str(root/'private/tzx-host-ed25519'),
        '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'UserKnownHostsFile='+str(root/'private/tablet_known_hosts'),
        'debian@192.168.77.2:/home/debian/dram-gpu-cooling-v2-installed-checkpoint.tar.gz', str(target)],
        capture_output=True, text=True, timeout=45)
    elapsed = time.monotonic()-started
    digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
    record = {'cycle': cycle, 'exit_code': result.returncode, 'seconds': round(elapsed, 3),
              'bytes': target.stat().st_size if target.is_file() else 0,
              'sha256': digest, 'default_rate': True, 'stderr': result.stderr}
    record['result'] = 'PASS' if result.returncode == 0 and digest == expected and record['bytes'] == snapshot['archive_bytes'] else 'FAIL'
    records.append(record)
    report.write_text(json.dumps({'scope': 'two bounded default-rate SCP reads; no kernel/USB setting changes',
        'earlier_disconnect_not_explained': True, 'transfers': records}, indent=2)+'\n')
    print('USB_DEFAULT_RATE_CHECKPOINT_TRANSFER', json.dumps(record), flush=True)
    assert record['result'] == 'PASS'
    target.unlink()
helper = [sys.executable, '-X', 'utf8', str(root/'tools/tablet_ssh.py')]
result = subprocess.run(helper+['--root', '--command',
    'cat /proc/sys/kernel/random/boot_id; systemctl --failed --no-legend; python3 /usr/local/lib/tzx-cpu-cooling/runtime.py verify',
    '--output', 'cpu-cooling-v2-usb-full-rate-final-health.txt', '--timeout', '35'],
    capture_output=True, text=True, encoding='utf8', timeout=45, check=True)
assert result.stdout.splitlines()[0] == snapshot['boot_id']
print('USB_TWO_DEFAULT_RATE_TRANSFERS_AND_UNCHANGED_BOOT_PASS', flush=True)
