"""Verify service stop and supervisor death restore DDR52 before re-entry."""
import json,subprocess,time
from pathlib import Path
unit='tzx-emmc-hs.service'
param=Path('/sys/module/tzx_emmc_hs_lease/parameters')
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=170)
def baseline():
    for _ in range(100):
        if not param.exists():break
        time.sleep(.1)
    assert not param.exists()
    ios=Path('/sys/kernel/debug/mmc0/ios').read_text()
    assert 'mmc DDR52' in ios and Path('/sys/kernel/debug/mmc0/clock').read_text().strip()=='25000000'
    return ios
def active():
    assert param.exists() and int((param/'fault').read_text())==0
    assert 'mmc HS200' in Path('/sys/kernel/debug/mmc0/ios').read_text()
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip()=='100000000'
events=[]
active();run('systemctl','stop',unit)
events.append(dict(action='normal stop',ios=baseline()))
run('systemctl','start',unit);active()
run('systemctl','kill','--kill-whom=main','--signal=SIGKILL',unit)
events.append(dict(action='supervisor SIGKILL and ExecStopPost',ios=baseline()))
run('systemctl','reset-failed',unit);run('systemctl','start',unit);active()
proof=dict(status='PASS',boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    events=events,restart_hs200_verified=True)
Path('/var/lib/tzx/emmc-hs-service-controls.json').write_text(json.dumps(proof,indent=2)+'\n')
print('HS200_SERVICE_STOP_SIGKILL_AND_RESTART_PASS',json.dumps(proof),flush=True)
