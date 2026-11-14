"""A board-scoped, RAM-only LZ4 swap device; never use an eMMC backing device."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser();p.add_argument('operation',choices=('start','stop','status'));a=p.parse_args()
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
def run(*args): return subprocess.check_output(args,text=True).strip()
device='/dev/zram0';sys=Path('/sys/block/zram0');size=2*1024**3
def active(): return [line.split() for line in Path('/proc/swaps').read_text().splitlines()[1:] if line.split()[0]==device]
if a.operation=='start':
    assert 'CONFIG_SWAP=y' in run('zcat','/proc/config.gz')
    for name,digest in json.loads(Path('/usr/local/lib/tzx-zram/native-installed.json').read_text()).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    if not active():
        run('modprobe','zram','num_devices=1')
        assert sys.exists() and (sys/'disksize').read_text().strip()=='0'
        (sys/'comp_algorithm').write_text('lz4')
        (sys/'disksize').write_text(str(size))
        assert not (sys/'backing_dev').exists() or (sys/'backing_dev').read_text().strip()=='none'
        run('mkswap','-L','TZX-zram',device);run('swapon','-p','100',device)
    assert active()[0][4]=='100'
    assert int((sys/'disksize').read_text())==size and '[lz4]' in (sys/'comp_algorithm').read_text()
    Path('/proc/sys/vm/swappiness').write_text('100')
    Path('/proc/sys/vm/page-cluster').write_text('0')
elif a.operation=='stop':
    if active(): run('swapoff',device)
    if sys.exists(): (sys/'reset').write_text('1')
state={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'active':bool(active()),
       'device':device,'ram_only':True,'logical_bytes':int((sys/'disksize').read_text()) if sys.exists() else 0,
       'algorithm':(sys/'comp_algorithm').read_text().strip() if sys.exists() else None,
       'swaps':Path('/proc/swaps').read_text(),'swappiness':Path('/proc/sys/vm/swappiness').read_text().strip(),
       'page_cluster':Path('/proc/sys/vm/page-cluster').read_text().strip()}
Path('/run/tzx-zram.json').write_text(json.dumps(state,indent=2)+'\n')
print(json.dumps(state,indent=2))
