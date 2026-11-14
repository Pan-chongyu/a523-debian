"""Keep qualified CPU policies in performance mode; native thermal caps win."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
assert os.geteuid()==0 and sys.argv[1:] in (['enable'],['restore'])
ROOT=Path('/usr/local/lib/tzx-performance-mode')
BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
POLICIES=[Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0,4)]
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
if sys.argv[1]=='restore':
    gpu=Path('/sys/class/devfreq/1800000.gpu')
    if gpu.exists():
        (gpu/'min_freq').write_text('150000000')
        Path('/sys/bus/platform/devices/1800000.gpu/power/control').write_text('auto')
    for policy in POLICIES:
        if policy.exists():
            (policy/'scaling_min_freq').write_text('120000')
            (policy/'scaling_governor').write_text('schedutil')
    print('AUTOMATIC_CPU_GOVERNOR_RESTORED',flush=True)
    raise SystemExit(0)
for name,digest in json.loads((ROOT/'manifest.json').read_text())['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
for attempt in range(100):
    try:
        owner=json.loads(Path('/run/tzx-cpu-dvfs.json').read_text())
        if owner['boot_id']==BOOT and owner['state']=='active' and all(
            (p/'scaling_driver').read_text().strip()=='tzx-a523-dvfs2' for p in POLICIES):break
    except (OSError,KeyError,json.JSONDecodeError):pass
    time.sleep(.2)
else:raise RuntimeError('CPU owner did not finish initializing')
assert [int((p/'cpuinfo_max_freq').read_text()) for p in POLICIES]==[1416000,1800000]
gpu=Path('/sys/class/devfreq/1800000.gpu')
for attempt in range(100):
    try:
        owner=json.loads(Path('/run/tzx-gpu-performance.json').read_text())
        if owner['boot_id']==BOOT and owner['state']=='active':break
    except (OSError,KeyError,json.JSONDecodeError):pass
    time.sleep(.2)
else:raise RuntimeError('GPU owner did not finish initializing')
assert (gpu/'governor').read_text().strip()=='simple_ondemand'
assert int(Path('/sys/module/tzx_gpu_devfreq_guard/parameters/fault').read_text())==0
assert Path('/sys/module/tzx_cpu_dvfs_cooling_v2/parameters/first_trip').read_text().strip()=='70000'
assert Path('/sys/module/tzx_cpu_dvfs_cooling_v2/parameters/second_trip').read_text().strip()=='80000'
for policy in POLICIES:
    (policy/'scaling_min_freq').write_text('120000')
    (policy/'scaling_governor').write_text('performance')
(gpu/'min_freq').write_text('600000000')
Path('/sys/bus/platform/devices/1800000.gpu/power/control').write_text('on')
record=dict(boot_id=BOOT,state='active',governors=[(p/'scaling_governor').read_text().strip() for p in POLICIES],
    requested_maximum_khz=[1416000,1800000],native_thermal_and_lease_caps_unchanged=True,
    user_preference='maximum qualified CPU/GPU performance including boot; no preload',
    gpu_requested_minimum_hz=600000000,gpu_runtime_power='on',browser_preload=False)
assert record['governors']==['performance','performance']
Path('/run/tzx-performance-mode.json').write_text(json.dumps(record,indent=2)+'\n')
print('PERSISTENT_QUALIFIED_CPU_PERFORMANCE_MODE_ACTIVE',json.dumps(record),flush=True)
