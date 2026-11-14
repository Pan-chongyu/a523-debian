"""Attach OPPs before the pinned Panfrost driver is allowed to probe."""
from pathlib import Path
from common import *

validate()
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_gpu_performance').exists()
run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard')
if PENDING.exists():
    assert __import__('json').loads(PENDING.read_text())['boot_id']==BOOT,'Unclean prior native GPU boot'
run('modprobe','governor_simpleondemand')
if not Path('/sys/module/tzx_gpu_devfreq_opps').exists():
    run('insmod',str(ROOT/'tzx_gpu_devfreq_opps.ko'))
run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','gpu-start',timeout=55)
assert DEVFREQ.exists()
assert (DEVFREQ/'governor').read_text().strip()=='simple_ondemand'
assert [int(v) for v in (DEVFREQ/'available_frequencies').read_text().split()]==[150000000,200000000,300000000,400000000,600000000]
cap_baseline()
if not PARAM.exists():run('insmod',str(ROOT/'tzx_gpu_devfreq_guard.ko'))
assert int((PARAM/'fault').read_text())==0
print('PANFROST_NATIVE_OPPS_AND_KERNEL_QOS_GUARD_READY',flush=True)
