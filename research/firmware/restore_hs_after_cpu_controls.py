"""Resume already-qualified HS200 after the CPU thermal inventory repair."""
import json,os,subprocess,time
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx')
source=state/'emmc-hs-revoked.json'
target=state/'emmc-hs-qualified.json'
assert not target.exists()
proof=json.loads(source.read_text())
assert proof['trial']['status']=='PASS'
assert proof['controls']['lease_expiry_verified'] and proof['controls']['post_expiry_direct_io_verified']
runtime=Path('/usr/local/lib/tzx-emmc-hs/runtime.py').read_text()
assert 'assert set(observed)==physical' in runtime
assert json.loads(Path('/run/tzx-cpu-dvfs.json').read_text())['state']=='active'
target.write_bytes(source.read_bytes())
subprocess.run(['systemctl','reset-failed','tzx-emmc-hs'],check=True)
subprocess.run(['systemctl','start','tzx-emmc-hs'],check=True,timeout=100)
for unused in range(40):
    status=json.loads(Path('/run/tzx-emmc-hs.json').read_text())
    if status.get('state')=='active':break
    time.sleep(.5)
assert status['state']=='active' and status['actual_hz']==100000000
assert 'mmc HS200' in Path('/sys/kernel/debug/mmc0/ios').read_text()
assert not subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip()
print('QUALIFIED_HS200_RESUMED_WITH_PHYSICAL_SENSOR_GUARD',json.dumps(status),flush=True)
