"""Shared pinned identity and hardware guards for native GPU integration."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path('/usr/local/lib/tzx-gpu-devfreq')
QUALIFIED=Path('/var/lib/tzx/gpu-devfreq-qualified.json')
PENDING=Path('/var/lib/tzx/gpu-devfreq-pending.json')
STATUS=Path('/run/tzx-gpu-performance.json')
PARAM=Path('/sys/module/tzx_gpu_devfreq_guard/parameters')
DEVFREQ=Path('/sys/class/devfreq/1800000.gpu')
BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def run(*args,timeout=40):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)


def atomic(path,value):
    temporary=path.with_suffix(path.suffix+'.new')
    assert not path.is_symlink()
    with temporary.open('w') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')
        os.fchmod(stream.fileno(),0o600);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def validate():
    assert os.geteuid()==0
    assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    proof=json.loads(QUALIFIED.read_text())
    assert proof['profile']==manifest['profile']=='Panfrost-native-150-600MHz-fixed-900mV'
    assert proof['trial']['status']=='PASS' and proof['trial']['baseline_restored']
    assert proof['trial']['error'] is None and proof['trial']['restoration_error'] is None
    return proof


def faults():
    return [line for line in run('dmesg').splitlines()
            if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b',line,re.I)]


def cap_baseline():
    if DEVFREQ.exists():
        (DEVFREQ/'min_freq').write_text('150000000')
        (DEVFREQ/'max_freq').write_text('200000000')
    if PARAM.exists():
        (PARAM/'maximum_mhz').write_text('200')
    PENDING.unlink(missing_ok=True)
    atomic(STATUS,dict(boot_id=BOOT,state='baseline',maximum_mhz=200,
        actual_mhz=int((DEVFREQ/'cur_freq').read_text())//1000000 if DEVFREQ.exists() else None,
        governor='simple_ondemand',clock_owner='Panfrost devfreq',voltage_changed=False))


def stop_guard():
    cap_baseline()
    if PARAM.exists():run('rmmod','tzx_gpu_devfreq_guard',timeout=15)
