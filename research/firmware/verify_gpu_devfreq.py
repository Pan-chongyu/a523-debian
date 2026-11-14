"""Trial native Panfrost OPPs, with watchdog and the installed GPU as fallback."""
import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

ROOT = Path('/home/debian/gpu-devfreq')
PARAM = Path('/sys/module/tzx_gpu_devfreq_guard/parameters')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
records = []
peaks = {}
watchdog = None
ping_stop = threading.Event()
thread = None
process = None
native = None
error = None
started = time.monotonic()


def run(*args, timeout=35, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout, **kwargs)


def faults():
    return [s for s in run('dmesg').splitlines()
            if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b', s, re.I)]


def record(**values):
    records.append(values)
    (ROOT/'trial-state.json').write_text(json.dumps(dict(boot_id=BOOT, records=records), indent=2)+'\n')
    print(json.dumps(values), flush=True)


def check():
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    assert not faults()
    if PARAM.exists():
        assert int((PARAM/'fault').read_text()) == 0
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        name, value = (zone/'type').read_text().strip(), int((zone/'temp').read_text())
        peaks[name] = max(peaks.get(name, 0), value)
        assert 0 < value < 73000, (name, value)


def safe_cap():
    if native and native.exists():
        (native/'min_freq').write_text('150000000')
        (native/'max_freq').write_text('200000000')


def unload_guard():
    safe_cap()
    if PARAM.exists():
        (PARAM/'maximum_mhz').write_text('200')
        run('rmmod', 'tzx_gpu_devfreq_guard')


def load_guard(*args):
    run('insmod', str(ROOT/'tzx_gpu_devfreq_guard.ko'), *args)
    assert int((PARAM/'fault').read_text()) == 0


def pixel():
    result = json.loads(run('python3', '/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py',
                           '--node', '/dev/dri/by-path/platform-tzx-de-scanout-card', timeout=18).splitlines()[-1])
    assert result['result'] == 'GPU_SHADER_AND_PIXEL_READBACK_PASS'
    return result


def bench(label, rate=None):
    global process
    log = ROOT/('bench-'+label+'.log')
    samples = []
    with log.open('w') as stream:
        process = subprocess.Popen(['runuser', '-u', 'debian', '--', 'env', 'DISPLAY=:0',
                                    'XAUTHORITY=/home/debian/.Xauthority', 'stdbuf', '-oL',
                                    'glmark2-es2', '--size', '640x480', '--off-screen',
                                    '-b', 'shading:shading=phong:duration=3',
                                    '-b', 'texture:texture-filter=linear:duration=3',
                                    '-b', 'buffer:duration=3'], stdout=stream, stderr=subprocess.STDOUT)
        end = time.monotonic()+35
        while process.poll() is None:
            check()
            assert time.monotonic() < end
            if PARAM.exists():
                (PARAM/'maximum_mhz').write_text('600')
            samples.append(int((native/'cur_freq').read_text()))
            time.sleep(.1)
        assert process.returncode == 0, log.read_text()
    text = log.read_text()
    assert 'Mali-G57' in text and 'llvmpipe' not in text.lower()
    scores = [int(v) for v in re.findall(r'FPS:\s*(\d+)', text)]
    assert len(scores) == 3, text
    if rate:
        assert rate in samples, (rate, sorted(set(samples)))
    record(check='GPU scenes', label=label, frequencies_hz=sorted(set(samples)), fps=scores,
           pixel=pixel())


def ping():
    while not ping_stop.wait(2):
        os.write(watchdog, b'.')


def interrupt(number, frame):
    raise RuntimeError('Signal '+str(number))


signal.signal(signal.SIGTERM, interrupt)
signal.signal(signal.SIGINT, interrupt)
try:
    assert os.geteuid() == 0
    assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
    assert not faults()
    watchdog = os.open('/dev/watchdog', os.O_WRONLY | os.O_CLOEXEC)
    support = bytearray(40)
    fcntl.ioctl(watchdog, 0x80285700, support, True)
    assert int.from_bytes(support[:4], 'little') & 0x100
    value = array.array('i', [16]); fcntl.ioctl(watchdog, 0xc0045706, value, True)
    thread = threading.Thread(target=ping, daemon=True); thread.start()
    record(check='watchdog', seconds=value[0])
    run('systemctl', 'stop', 'tzx-gpu-performance.service')
    run('systemctl', 'stop', 'lightdm')
    run('rmmod', 'panfrost', timeout=15)
    run('modprobe', 'governor_simpleondemand')
    run('insmod', str(ROOT/'tzx_gpu_devfreq_opps.ko'))
    run('insmod', '/usr/local/lib/tzx-dram-gpu/panfrost.ko', 'tzx_dma32=1')
    native = Path('/sys/class/devfreq/1800000.gpu')
    assert native.exists(), run('dmesg')[-7000:]
    assert (native/'governor').read_text().strip() == 'simple_ondemand'
    assert [int(v) for v in (native/'available_frequencies').read_text().split()] == [150000000,200000000,300000000,400000000,600000000]
    safe_cap(); load_guard()
    run('systemctl', 'start', 'lightdm')
    time.sleep(5)
    for mhz in (150,200,300,400,600):
        check()
        (PARAM/'maximum_mhz').write_text('600')
        hz = mhz*1000000
        (native/'max_freq').write_text(str(hz))
        (native/'min_freq').write_text(str(hz))
        bench(str(mhz), hz)
        (native/'min_freq').write_text('150000000')
    (native/'max_freq').write_text('600000000')
    bench('automatic')
    run('systemctl', 'stop', 'lightdm')
    # No clients: governor reaches its lowest OPP, followed by runtime suspend.
    time.sleep(3)
    record(check='idle', rate_hz=int((native/'cur_freq').read_text()),
           runtime_status=Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip())
    unload_guard(); load_guard('lease_seconds=3', 'first_trip=30000')
    (native/'max_freq').write_text('600000000')
    (PARAM/'maximum_mhz').write_text('600')
    assert int((PARAM/'limit_mhz').read_text()) == 400
    record(check='first thermal cap', maximum_mhz=400)
    try:
        (PARAM/'maximum_mhz').write_text('800')
        raise AssertionError('Unqualified rate accepted')
    except OSError:
        pass
    time.sleep(4)
    assert int((PARAM/'limit_mhz').read_text()) == 200
    record(check='expired kernel lease', maximum_mhz=200)
    unload_guard(); load_guard('first_trip=30000', 'second_trip=35000')
    (native/'max_freq').write_text('600000000')
    (PARAM/'maximum_mhz').write_text('600')
    assert int((PARAM/'limit_mhz').read_text()) == 200
    record(check='second thermal cap', maximum_mhz=200)
    check()
except BaseException as caught:
    error = repr(caught)
    print('TRIAL_ERROR', error, flush=True)
finally:
    if process and process.poll() is None:
        process.terminate()
        try: process.wait(5)
        except subprocess.TimeoutExpired: process.kill(); process.wait(3)
    restoration_error = None
    try:
        unload_guard()
        run('systemctl', 'stop', 'lightdm')
        if Path('/sys/module/panfrost').exists(): run('rmmod', 'panfrost', timeout=15)
        if Path('/sys/module/tzx_gpu_devfreq_opps').exists(): run('rmmod', 'tzx_gpu_devfreq_opps')
        run('insmod', '/usr/local/lib/tzx-dram-gpu/panfrost.ko', 'tzx_dma32=1')
        run('systemctl', 'start', 'lightdm')
        run('systemctl', 'start', 'tzx-gpu-performance.service')
        check()
        record(check='original desktop restored', pixel=pixel())
    except BaseException as caught:
        restoration_error = repr(caught)
        print('RESTORE_ERROR', restoration_error, flush=True)
    if watchdog is not None:
        ping_stop.set()
        if thread: thread.join(3)
        os.write(watchdog, b'V'); os.close(watchdog)
    result = dict(status='PASS' if not error and not restoration_error else 'FAIL', boot_id=BOOT,
                  error=error, restoration_error=restoration_error, records=records,
                  peak_temperatures_mc=peaks, elapsed_s=round(time.monotonic()-started,2),
                  baseline_restored=not restoration_error)
    (ROOT/'trial-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('GPU_NATIVE_DEVFREQ_TRIAL', json.dumps(result), flush=True)
    if error or restoration_error: raise SystemExit(1)
