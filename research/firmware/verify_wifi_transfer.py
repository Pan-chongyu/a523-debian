"""Measure the same local WLAN path and check every transferred byte."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--label', required=True)
parser.add_argument('--cycles', type=int, default=2)
args = parser.parse_args()
assert args.label and all(c.isalnum() or c == '-' for c in args.label)
assert 1 <= args.cycles <= 4
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert 'dev wlan0' in subprocess.check_output(['ip', 'route', 'get', '10.0.2.40'], text=True)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
endpoint = 'http://10.0.2.40:18765'
rows = []
payload = os.urandom(8 * 1024 * 1024)
digest = hashlib.sha256(payload).hexdigest()
before = Path('/sys/kernel/debug/mmc1/err_stats').read_text()
for cycle in range(args.cycles):
    for direction in ('download', 'upload'):
        start = time.monotonic()
        if direction == 'download':
            with opener.open(endpoint + '/data', timeout=45) as response:
                data = response.read()
                assert len(data) == len(payload)
                assert hashlib.sha256(data).hexdigest() == response.headers['X-TZX-SHA256']
        else:
            request = urllib.request.Request(endpoint + '/upload', data=payload,
                                             headers={'X-TZX-SHA256': digest}, method='POST')
            with opener.open(request, timeout=45) as response:
                assert response.read() == b'OK'
        elapsed = time.monotonic() - start
        row = {'cycle': cycle + 1, 'direction': direction, 'bytes': len(payload),
               'seconds': round(elapsed, 3), 'Mbit_per_second': round(len(payload)*8/elapsed/1e6, 3),
               'sha256': 'PASS'}
        rows.append(row)
        print('WIFI_TRANSFER', json.dumps(row), flush=True)
after = Path('/sys/kernel/debug/mmc1/err_stats').read_text()
assert not any(int(value) for value in re.findall(r':\s*(\d+)', after)), after
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
report = {'label': args.label, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'transfers': rows, 'mmc_ios': Path('/sys/kernel/debug/mmc1/ios').read_text(),
          'errors_before': before, 'errors_after': after, 'same_local_wifi_path': True}
Path('/home/debian/wifi-transfer-' + args.label + '.json').write_text(json.dumps(report, indent=2) + '\n')
print('WIFI_LOCAL_TRANSFER_AND_SDIO_INTEGRITY_PASS', json.dumps(report), flush=True)
