"""Prove an abandoned lease restores the standard card protocol and data I/O."""
import json,os,subprocess,time
from pathlib import Path
root=Path('/home/debian/hs-kernel')
param=Path('/sys/module/tzx_emmc_hs_lease/parameters')
assert os.geteuid()==0 and not param.exists()
subprocess.run(['insmod',str(root/'tzx_emmc_hs_lease.ko'),'lease_seconds=4'],check=True)
try:
    subprocess.run(['/run/emmc-transition-guard','200,100'],check=True,timeout=135)
    assert 'mmc HS200' in Path('/sys/kernel/debug/mmc0/ios').read_text()
    deadline=time.monotonic()+12
    while time.monotonic()<deadline and int((param/'mode').read_text())!=0:time.sleep(.2)
    assert int((param/'mode').read_text())==0 and int((param/'fault').read_text())==0
    assert 'mmc DDR52' in Path('/sys/kernel/debug/mmc0/ios').read_text()
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip()=='25000000'
    result=subprocess.check_output(['python3','/home/debian/verify_emmc_hs.py','io-worker'],text=True,timeout=45)
    controls=dict(lease_expiry_verified=True,post_expiry_direct_io_verified=True,transfers=json.loads(result))
    (root/'controls-200-100.json').write_text(json.dumps(controls,indent=2)+'\n')
    print('HS200_LEASE_EXPIRY_PROTOCOL_AND_DIRECT_IO_PASS',json.dumps(controls),flush=True)
finally:
    subprocess.run(['rmmod','tzx_emmc_hs_lease'],check=True,timeout=30)
