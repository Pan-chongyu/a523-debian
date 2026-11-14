"""Renew the kernel QoS ceiling; Panfrost alone selects the actual OPP."""
import signal
import threading
from common import *

stop=threading.Event()
signal.signal(signal.SIGTERM,lambda *_:stop.set())
signal.signal(signal.SIGINT,lambda *_:stop.set())
try:
    validate()
    if PENDING.exists():assert json.loads(PENDING.read_text())['boot_id']==BOOT
    run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard')
    health=json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())
    assert health['boot_id']==BOOT and health['status']=='PASS'
    assert PARAM.exists() and DEVFREQ.exists()
    assert not Path('/sys/module/tzx_gpu_performance').exists()
    assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip() in ('auto','on')
    for name,value in (('first_trip','65000'),('second_trip','70000'),('fault_trip','85000'),('lease_seconds','30')):
        assert (PARAM/name).read_text().strip()==value
    atomic(PENDING,dict(boot_id=BOOT,state='running',profile='Panfrost-native-150-600MHz-fixed-900mV'))
    (DEVFREQ/'min_freq').write_text('600000000')
    (PARAM/'maximum_mhz').write_text('600')
    (DEVFREQ/'max_freq').write_text('600000000')
    while not stop.is_set():
        assert Path('/var/lib/tzx/gpu-qualified').exists()
        assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
        assert not faults()
        assert int((PARAM/'fault').read_text())==0
        assert (DEVFREQ/'governor').read_text().strip()=='simple_ondemand'
        (PARAM/'maximum_mhz').write_text('600')
        atomic(STATUS,dict(boot_id=BOOT,state='active',maximum_mhz=600,
            actual_mhz=int((DEVFREQ/'cur_freq').read_text())//1000000,
            effective_maximum_mhz=int((PARAM/'limit_mhz').read_text()),
            maximum_temperature_mc=int((PARAM/'temperature_mc').read_text()),
            peak_temperature_mc=int((PARAM/'peak_temperature_mc').read_text()),
            runtime_status=Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip(),
            governor='simple_ondemand',clock_owner='Panfrost devfreq',
            thermal_caps_mc=[65000,70000],lease_seconds=30,voltage_changed=False,PLL_changed=False))
        stop.wait(5)
except BaseException as error:
    atomic(Path('/var/lib/tzx/gpu-devfreq-failure.json'),dict(boot_id=BOOT,error=repr(error)))
    if QUALIFIED.exists():QUALIFIED.replace('/var/lib/tzx/gpu-devfreq-revoked.json')
    raise
finally:
    cap_baseline()
