"""Qualify compressed swap before enabling its boot unit."""
import json
import os
from pathlib import Path
import shutil
import subprocess

assert os.geteuid()==0
root=Path('/usr/local/lib/tzx-zram')
assert not Path('/var/lib/tzx/zram-qualified.json').exists()
assert not Path('/etc/systemd/system/tzx-zram.service').exists()
assert not root.exists() or {p.name for p in root.iterdir()}<={'runtime.py','native-installed.json'}
root.mkdir(exist_ok=True)
source=Path('/home/debian/zram-stage')
shutil.copyfile(source/'tzx_zram.py',root/'runtime.py')
shutil.copyfile('/home/debian/extended-kernel/native-installed.json',root/'native-installed.json')
before={p:Path('/proc/sys/vm/'+p).read_text().strip() for p in ('swappiness','page-cluster')}
def run(*args,**kwargs): return subprocess.run(args,check=True,text=True,**kwargs)
def counters():
    return {row.split()[0]:int(row.split()[1]) for row in Path('/proc/vmstat').read_text().splitlines() if row.startswith(('pswpin ','pswpout '))}
initial=counters()
try:
    run('python3',str(root/'runtime.py'),'start',timeout=30)
    run('chmod','755',str(source/'verify-zram'))
    result=run(str(source/'verify-zram'),timeout=100,capture_output=True)
    print(result.stdout,flush=True)
    assert 'EVERY_WORD_VERIFIED' in result.stdout
    final=counters();assert final['pswpin']>initial['pswpin']+1000 and final['pswpout']>initial['pswpout']+1000
    backing=Path('/sys/block/zram0/backing_dev')
    assert not backing.exists() or backing.read_text().strip()=='none'
    Path('/var/lib/tzx/zram-qualified.json').write_text(json.dumps({'status':'PASS','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'initial_vmstat':initial,'final_vmstat':final,'full_256MiB_verified':True,'output':result.stdout,'previous_sysctl':before},indent=2)+'\n')
    shutil.copyfile(source/'tzx-zram.service','/etc/systemd/system/tzx-zram.service')
    Path('/etc/sysctl.d/60-tzx-zram.conf').write_text('# LZ4 RAM swap; no eMMC swap or writeback.\nvm.swappiness=100\nvm.page-cluster=0\n')
    run('systemctl','daemon-reload');run('systemctl','enable','--now','tzx-zram.service',timeout=45)
    run('python3',str(root/'runtime.py'),'status',timeout=20)
    print('ZRAM_2_GIB_LZ4_ACTUAL_SWAP_OUT_IN_VERIFIED_AND_ENABLED',flush=True)
except BaseException:
    run('python3',str(root/'runtime.py'),'stop',timeout=60)
    for p,v in before.items(): Path('/proc/sys/vm/'+p).write_text(v)
    raise
os.sync()
