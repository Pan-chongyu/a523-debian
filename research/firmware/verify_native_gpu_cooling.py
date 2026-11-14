"""Check native devfreq cooling against real sensors with lowered test trips."""
import json,os,subprocess,time
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
root=Path('/usr/local/lib/tzx-cpu-full')
devfreq=Path('/sys/class/devfreq/1800000.gpu')
assert devfreq.exists()
result={}


def run(*args,timeout=85):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)


def unload():
    for module in ('tzx_cpu_dvfs_cooling_v2','tzx_cpufreq_dvfs_v2'):
        if Path('/sys/module',module).exists():run('rmmod',module,timeout=20)


def load(*parameters):
    run('insmod',str(root/'tzx_cpufreq_dvfs_v2.ko'))
    run('insmod',str(root/'tzx_cpu_dvfs_cooling_v2.ko'),*parameters)


def gpu_cooling():
    return next(p for p in Path('/sys/class/thermal').glob('cooling_device*')
                if (p/'type').read_text().strip()=='devfreq-1800000.gpu')


run('systemctl','stop','tzx-emmc-hs','tzx-cpu-dvfs')
run('systemctl','start','tzx-cpufreq','tzx-cpu-cooling')
run('systemctl','stop','tzx-cpu-cooling','tzx-cpufreq')
try:
    (devfreq/'min_freq').write_text('150000000')
    for label,parameters,state,hz in (
        ('first',('gpu_first_trip=30000',),1,400000000),
        ('second',('gpu_first_trip=30000','gpu_second_trip=35000'),3,200000000)):
        load(*parameters)
        cooler=gpu_cooling()
        for attempt in range(30):
            if int((cooler/'cur_state').read_text())==state:break
            time.sleep(.5)
        assert int((cooler/'cur_state').read_text())==state
        assert int((devfreq/'max_freq').read_text())==hz, (devfreq/'max_freq').read_text()
        zone=next(p for p in Path('/sys/class/thermal').glob('thermal_zone*') if (p/'type').read_text().strip()=='tzx-board-thermal')
        assert int((zone/'temp').read_text())>35000
        result[label]=dict(native_cooling_state=state,effective_max_hz=hz,
            actual_temperature_mc=int((zone/'temp').read_text()),emulated_temperature=False)
        unload()
finally:
    unload()
    run('systemctl','start','tzx-cpufreq','tzx-cpu-cooling')
    run('systemctl','start','tzx-cpu-dvfs')
    for attempt in range(80):
        state_path=Path('/run/tzx-cpu-dvfs.json')
        if state_path.exists() and json.loads(state_path.read_text()).get('state')=='active':break
        time.sleep(.5)
    assert json.loads(state_path.read_text())['maximum_khz']==[1416000,1800000]
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
    assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
result.update(status='PASS',boot_id=boot,production_trips_restored=True)
Path('/var/lib/tzx/native-gpu-cooling-controls.json').write_text(json.dumps(result,indent=2)+'\n')
print('NATIVE_DEVFREQ_THERMAL_BINDINGS_AND_QOS_CAPS_PASS',json.dumps(result),flush=True)
