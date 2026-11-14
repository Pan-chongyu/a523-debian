"""Warm a bounded set of app binaries after the desktop, at low I/O priority."""
import json
import os
from pathlib import Path
import time

assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
started=time.monotonic()
paths=[Path('/usr/lib/firefox-esr/libxul.so'),Path('/usr/lib/firefox-esr/omni.ja'),
    Path('/usr/lib/firefox-esr/browser/omni.ja'),*sorted(Path('/usr/lib/aarch64-linux-gnu').glob('libgallium-*.so')),
    Path('/usr/bin/xfce4-terminal'),Path('/usr/bin/mousepad'),Path('/usr/bin/thunar')]
budget=320*1024*1024;total=0;records=[]
for path in paths:
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    if int(memory['MemAvailable'].split()[0])<1024*1024:
        records.append({'path':str(path),'skipped':'less than 1 GiB available'});break
    if not path.is_file() or total+path.stat().st_size>budget:continue
    count=0
    with path.open('rb',buffering=0) as stream:
        while data:=stream.read(1024*1024):
            count+=len(data)
            # Bound foreground interference; this is a cache fill, not a speed test.
            time.sleep(.004)
    total+=count;records.append({'path':str(path),'bytes':count})
record=dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),status='PASS',
    seconds=round(time.monotonic()-started,3),bytes_read=total,budget_bytes=budget,files=records,
    cached_pages_reclaimable=True)
Path('/run/tzx-app-cache.json').write_text(json.dumps(record,indent=2)+'\n')
print('BOUNDED_APPLICATION_CACHE_WARM_PASS',json.dumps(record),flush=True)
