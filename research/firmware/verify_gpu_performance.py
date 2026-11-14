"""Compare fixed-parent GPU rates on the live desktop with bounded guards."""
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

ROOT = Path('/home/debian/gpu-performance')
PARAM = Path('/sys/module/tzx_gpu_performance/parameters')
RESULT = ROOT / 'trial-result.json'
STATE = ROOT / 'trial-state.json'
records = []
started = time.monotonic()
stop_ping = threading.Event()
watchdog = None
ping_thread = None
active = None
boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
taint = int(Path('/proc/sys/kernel/tainted').read_text())
assert taint == 4096
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert (PARAM / 'active_only').read_text().strip() == 'N'
assert int((PARAM / 'actual_mhz').read_text()) == 200
sentinel = os.urandom(128 * 1024 * 1024)
sentinel_hash = hashlib.sha256(sentinel).digest()
critical = [Path('/usr/lib/aarch64-linux-gnu') / name for name in (
    'libc.so.6', 'libgbm.so.1.0.0', 'libEGL.so.1.1.0')]
critical += list(Path('/usr/lib/aarch64-linux-gnu').glob('libgallium-*.so'))
hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in critical}
zones = list(Path('/sys/class/thermal').glob('thermal_zone*'))
peaks = {}

def faults():
    return [s for s in subprocess.check_output(['dmesg'], text=True).splitlines()
            if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|watchdog: BUG', s, re.I)]

initial_faults = faults()
assert not initial_faults, initial_faults

def state(**extra):
    STATE.write_text(json.dumps(dict(boot_id=boot_id, elapsed=round(time.monotonic()-started, 2),
                                    records=records, peaks_mc=peaks, **extra), indent=2)+'\n')

def guard(mhz):
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot_id
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == taint
    assert int((PARAM / 'fault').read_text()) == 0
    assert faults() == initial_faults
    assert hashlib.sha256(sentinel).digest() == sentinel_hash, 'RAM sentinel changed'
    values = {p.joinpath('type').read_text().strip(): int(p.joinpath('temp').read_text()) for p in zones}
    for name, value in values.items():
        assert 0 < value < 65000, (name, value)
        peaks[name] = max(peaks.get(name, 0), value)
    for p, digest in hashes.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, str(p)
    (PARAM / 'requested_mhz').write_text(str(mhz))
    assert int((PARAM / 'actual_mhz').read_text()) == mhz

def ping_watchdog():
    while not stop_ping.wait(2):
        os.write(watchdog, b'.')

def interrupt(signum, frame):
    raise RuntimeError('Interrupted by signal '+str(signum))

signal.signal(signal.SIGTERM, interrupt)
signal.signal(signal.SIGINT, interrupt)
try:
    watchdog = os.open('/dev/watchdog', os.O_WRONLY | os.O_CLOEXEC)
    support = bytearray(40)
    fcntl.ioctl(watchdog, 0x80285700, support, True)
    assert int.from_bytes(support[:4], 'little') & 0x100, 'Watchdog lacks magic close'
    timeout = array.array('i', [16])
    fcntl.ioctl(watchdog, 0xc0045706, timeout, True)
    assert timeout[0] >= 10
    ping_thread = threading.Thread(target=ping_watchdog, daemon=True)
    ping_thread.start()
    print('HARDWARE_WATCHDOG_SECONDS', timeout[0], flush=True)
    for mhz in (200, 300, 400, 600, 600):
        guard(mhz)
        index = len(records)+1
        log_path = ROOT / ('scenes-%d-%dMHz.log' % (index, mhz))
        command = ['runuser', '-u', 'debian', '--', 'env', 'DISPLAY=:0',
                   'XAUTHORITY=/home/debian/.Xauthority', 'stdbuf', '-oL', '-eL',
                   'glmark2-es2', '--size', '640x480', '--off-screen', '-b', ':duration=1']
        tick = time.monotonic()
        with log_path.open('w') as log:
            active = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            state(stage='running', mhz=mhz, pid=active.pid)
            print('BEGIN', index, mhz, flush=True)
            while active.poll() is None:
                guard(mhz)
                assert time.monotonic()-tick < 180, 'Scene deadline'
                time.sleep(2)
            assert active.returncode == 0, active.returncode
        text = log_path.read_text()
        assert 'Mali-G57 (Panfrost)' in text and 'Error:' not in text, text
        score = re.search(r'glmark2 Score:\s*(\d+)', text)
        assert score, text
        record = {'mhz': mhz, 'score': int(score[1]), 'elapsed': round(time.monotonic()-tick, 2),
                  'scene_count': len(re.findall(r'FPS:', text)), 'log': log_path.name}
        assert record['scene_count'] >= 20, record
        records.append(record)
        guard(mhz)
        print('PASS', json.dumps(record), flush=True)
        (PARAM / 'requested_mhz').write_text('200')
        state(stage='between-scenes')
    guard(200)
    result = {'status': 'PASS', 'boot_id': boot_id, 'records': records,
              'peaks_mc': peaks, 'ram_sentinel_bytes': len(sentinel),
              'critical_hashes': {str(p): h for p, h in hashes.items()},
              'new_gpu_faults': [], 'kernel_taint': taint,
              'elapsed': round(time.monotonic()-started, 2)}
    RESULT.write_text(json.dumps(result, indent=2)+'\n')
    print('GPU_PERFORMANCE_TRIAL_PASS', json.dumps(result), flush=True)
except BaseException as error:
    state(stage='FAILED', error=repr(error))
    print('GPU_PERFORMANCE_TRIAL_FAILED', repr(error), flush=True)
    raise
finally:
    if active is not None and active.poll() is None:
        active.terminate()
        try:
            active.wait(timeout=5)
        except subprocess.TimeoutExpired:
            active.kill()
            active.wait()
    if PARAM.exists():
        (PARAM / 'requested_mhz').write_text('200')
    stop_ping.set()
    if ping_thread:
        ping_thread.join(timeout=5)
    if watchdog is not None:
        os.write(watchdog, b'V')
        os.close(watchdog)
