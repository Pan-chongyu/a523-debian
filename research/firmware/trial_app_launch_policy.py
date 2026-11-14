"""Run bounded application A/B trials and restore the original CPU policy."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('mode',choices=('baseline','performance','floor','cache','boost'))
p.add_argument('--rounds',type=int,default=3)
p.add_argument('--label-prefix',default='')
a=p.parse_args()
assert os.geteuid()==0
policies=[Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0,4)]
assert all((p/'scaling_driver').read_text().strip()=='tzx-a523-dvfs2' for p in policies)
assert [int((p/'scaling_max_freq').read_text()) for p in policies]==[1416000,1800000]
assert Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/clock_fault').read_text().strip()=='0'
subprocess.run(['systemctl','is-active','--quiet','tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs'],check=True)
before=[{k:(p/k).read_text().strip() for k in ('scaling_governor','scaling_min_freq')} for p in policies]
kernel=subprocess.check_output(['dmesg'],text=True)
assert 'js fault' not in kernel and 'job timeout' not in kernel
label=a.label_prefix+a.mode+'-direct-'+Path('/proc/sys/kernel/random/boot_id').read_text().strip()[:8]
started=time.monotonic()
try:
    if a.mode=='performance':
        for policy in policies:(policy/'scaling_governor').write_text('performance')
    elif a.mode=='floor':
        for policy,floor in zip(policies,(792000,1008000)):(policy/'scaling_min_freq').write_text(str(floor))
    command=['python3','/home/debian/profile_app_launch.py','--label',label,'--apps','terminal','browser','--rounds',str(a.rounds)]
    if a.mode=='cache':command+=['--browser-cache','on']
    if a.mode=='boost':command+=['--boost']
    log=Path('/home/debian/app-launch-profile')/(label+'-trial.log')
    with log.open('w') as stream:subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=160,check=True)
    record=json.loads(log.with_name(label+'.json').read_text())
    assert record['summary']
    assert subprocess.check_output(['dmesg'],text=True)==kernel,'new kernel messages during trial'
    record['trial_mode']=a.mode
    record['trial_seconds']=round(time.monotonic()-started,2)
    log.with_name(label+'.json').write_text(json.dumps(record,indent=2)+'\n')
    print('APP_LAUNCH_POLICY_TRIAL_PASS',json.dumps({k:record[k] for k in ('label','summary','policy','trial_seconds')}),flush=True)
finally:
    for policy,saved in zip(policies,before):
        if policy.exists():
            (policy/'scaling_min_freq').write_text(saved['scaling_min_freq'])
            (policy/'scaling_governor').write_text(saved['scaling_governor'])
    print('ORIGINAL_CPU_GOVERNOR_AND_FLOOR_RESTORED',flush=True)
