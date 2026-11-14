"""Install/remove only the individually qualified eMMC clock service."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert len(sys.argv) == 2 and sys.argv[1] in ('install','restore')
ROOT = Path('/usr/local/lib/tzx-emmc-performance')
STATE = Path('/var/lib/tzx/emmc-performance-installed.json')
QUALIFIED = Path('/var/lib/tzx/emmc-performance-qualified.json')
UNIT = 'tzx-emmc-performance.service'

def run(*command):
    subprocess.run(command,check=True,timeout=65)

if sys.argv[1] == 'restore':
    state = json.loads(STATE.read_text())
    run('systemctl','disable','--now',UNIT)
    assert not Path('/sys/module/tzx_emmc_performance').exists()
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
    for name,digest in state['manifest']['files'].items():
        p = Path(name)
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest,name
        p.unlink()
    (ROOT/'manifest.json').unlink()
    if not any(ROOT.iterdir()):
        ROOT.rmdir()
    QUALIFIED.unlink(missing_ok=True)
    run('systemctl','daemon-reload')
    state['state'] = 'restored-original-25MHz'
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    print('EMMC_PERFORMANCE_UNINSTALLED_ORIGINAL_25MHZ')
    raise SystemExit(0)

assert not ROOT.exists() and not STATE.exists()
assert not (Path('/etc/systemd/system')/UNIT).exists()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
trial = json.loads(Path('/home/debian/emmc-performance/trial-result.json').read_text())
assert trial['status'] == 'PASS' and trial['boot_id'] == boot
assert trial['lease_expiry_restores_25MHz'] and trial['unload_restores_25MHz']
assert [r['requested_mhz'] for r in trial['records']] == [25,33,40,50,52,50]
assert all(len(r['transfers']) == 2 for r in trial['records'])
assert trial['module_sha256'] == '8db02845e4630a11b711145cf5c4403d334416244807e519c85755d5a7a5a878'
assert min(t['read_MiB_s'] for r in trial['records'] if r['requested_mhz'] == 50 for t in r['transfers']) > 70
with tarfile.open('/home/debian/emmc-performance-runtime.tar.gz') as archive:
    members = archive.getmembers()
    expected = {'usr/local/lib/tzx-emmc-performance/'+n for n in
                ('tzx_emmc_performance.ko','runtime.py','cleanup.py','manifest.json')}
    expected.add('etc/systemd/system/'+UNIT)
    assert {m.name for m in members} == expected and len(members) == len(expected)
    assert all(m.isfile() and '..' not in Path(m.name).parts for m in members)
    for member in members:
        target = Path('/')/member.name
        assert not target.exists() and not target.is_symlink()
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(archive.extractfile(member).read())
        target.chmod(0o644)
manifest = json.loads((ROOT/'manifest.json').read_text())
for name,digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest,name
QUALIFIED.write_text(json.dumps({'trial':trial,'manifest':manifest,
    'scope':'online tests passed; this eMMC service not yet reboot-tested'},indent=2)+'\n')
STATE.write_text(json.dumps({'state':'installed-online-qualified','manifest':manifest,
    'installed_boot_id':boot,'normal_reboot_verified':False,'boot_areas_changed':False},indent=2)+'\n')
run('systemctl','daemon-reload')
run('systemctl','enable','--now',UNIT)
for unused in range(100):
    p = Path('/run/tzx-emmc-performance.json')
    if p.exists():
        observed = json.loads(p.read_text())
        if observed['boot_id'] == boot and observed['state'] == 'active':
            break
    time.sleep(0.25)
else:
    raise RuntimeError('eMMC performance controller not ready')
print('EMMC_PERFORMANCE_DDR52_50MHZ_INSTALLED',json.dumps(observed))
