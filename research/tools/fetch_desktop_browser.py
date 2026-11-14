"""Fetch the exact APT-authenticated Debian package through its CDN mirror."""
from pathlib import Path
import hashlib
import time
import urllib.request

name = 'firefox-esr_153.6.0esr-1~deb13u1_arm64.deb'
expected = '5ad1884bff1cf3a5a9e50c0a111101fa9a2cd9a4232437a7a790ed2333e1ccdb'
target = Path(__file__).resolve().parents[1] / 'build' / name
url = 'https://deb.debian.org/debian-security/pool/updates/main/f/firefox-esr/' + name
started = time.monotonic()
with urllib.request.urlopen(url, timeout=30) as response, target.with_suffix('.part').open('wb') as output:
    total = 0
    while data := response.read(1024 * 1024):
        output.write(data)
        total += len(data)
        if total % (8 * 1024 * 1024) == 0:
            print(total, 'bytes', round(time.monotonic()-started, 1), 'seconds', flush=True)
assert total == 71968932
assert hashlib.sha256(target.with_suffix('.part').read_bytes()).hexdigest() == expected
target.with_suffix('.part').replace(target)
print('APT_PACKAGE_SHA256_VERIFIED', total, round(time.monotonic()-started, 1), flush=True)
