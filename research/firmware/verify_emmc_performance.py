"""Bounded DDR52 clocks; O_DIRECT scratch-file I/O and automatic low-clock restore."""
import array
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path('/home/debian/emmc-performance')
FILE = ROOT/'performance-scratch.bin'
SIZE = 128*1024*1024

if len(sys.argv) == 2 and sys.argv[1] == 'io-worker':
    assert FILE.is_file() and FILE.stat().st_size == SIZE
    expected = hashlib.shake_256(b'TZX exact-CID DDR52 scratch v1').digest(SIZE)
    digest = hashlib.sha256(expected).hexdigest()
    buffer = mmap.mmap(-1, SIZE)
    results = []
    fd = os.open(FILE, os.O_RDWR | os.O_DIRECT)
    try:
        for repeat in (1,2):
            buffer[:] = expected
            start = time.monotonic()
            assert os.pwritev(fd, [buffer], 0) == SIZE
            os.fsync(fd)
            seconds_write = time.monotonic()-start
            buffer[:] = bytes(SIZE)
            start = time.monotonic()
            assert os.preadv(fd, [buffer], 0) == SIZE
            seconds_read = time.monotonic()-start
            assert hashlib.sha256(buffer).hexdigest() == digest, 'Direct read SHA256 mismatch'
            results.append({'repeat': repeat, 'bytes': SIZE, 'sha256': digest,
                'write_MiB_s': round(SIZE/1048576/seconds_write,3),
                'read_MiB_s': round(SIZE/1048576/seconds_read,3),
                'write_seconds': round(seconds_write,3), 'read_seconds': round(seconds_read,3)})
        print('DIRECT_SCRATCH_IO_PASS', json.dumps(results), flush=True)
    finally:
        os.close(fd)
        buffer.close()
    raise SystemExit(0)

assert len(sys.argv) == 1 and os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof = json.loads(Path('/var/lib/tzx/performance-installed-validation.json').read_text())
assert proof['status'] == 'PASS' and proof['boot_id'] == BOOT
ROOT.mkdir(exist_ok=True)
assert not FILE.exists()
assert not Path('/sys/module/tzx_emmc_performance').exists()
assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
assert hashlib.sha256((ROOT/'tzx_emmc_performance.ko').read_bytes()).hexdigest() == '8db02845e4630a11b711145cf5c4403d334416244807e519c85755d5a7a5a878'
fd = os.open(FILE, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.posix_fallocate(fd, 0, SIZE)
    os.fsync(fd)
finally:
    os.close(fd)
PARAM = Path('/sys/module/tzx_emmc_performance/parameters')
records, peaks = [], {}
started = time.monotonic()
watchdog = None
stop_ping = threading.Event()
ping = None
child = None
loaded = False
sentinel = os.urandom(64*1024*1024)
sentinel_hash = hashlib.sha256(sentinel).digest()
outcome = None

def run(*args, timeout=40):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    assert p.returncode == 0, (args, p.returncode, p.stdout[-2000:], p.stderr[-1000:])
    return p.stdout

def sample():
    assert time.monotonic()-started < 480
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    assert hashlib.sha256(sentinel).digest() == sentinel_hash
    assert int((PARAM/'fault').read_text()) == 0
    assert Path('/sys/kernel/debug/mmc0/err_state').read_text().strip() == '0'
    errors = [s for s in run('dmesg').splitlines() if re.search(
        r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|mmc0.*(error|timeout|CRC)|I/O error|EXT4-fs error', s, re.I)]
    assert not errors, errors
    for p in Path('/sys/class/thermal').glob('thermal_zone*'):
        name, temp = (p/'type').read_text().strip(), int((p/'temp').read_text())
        assert 0 < temp < 70000, (name,temp)
        peaks[name] = max(peaks.get(name,0), temp)
    for name in ('screen_buffer_errors', 'screen_panel_errors'):
        assert int((Path('/sys/module/tzx_display/parameters')/name).read_text()) == 0

def ping_watchdog():
    while not stop_ping.wait(2):
        os.write(watchdog, b'.')

def interrupted(signum, frame):
    raise RuntimeError('Interrupted '+str(signum))

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
try:
    watchdog = os.open('/dev/watchdog', os.O_WRONLY | os.O_CLOEXEC)
    support = bytearray(40)
    fcntl.ioctl(watchdog, 0x80285700, support, True)
    assert int.from_bytes(support[:4], 'little') & 0x100
    timeout = array.array('i', [16])
    fcntl.ioctl(watchdog, 0xc0045706, timeout, True)
    ping = threading.Thread(target=ping_watchdog, daemon=True)
    ping.start()
    run('insmod', str(ROOT/'tzx_emmc_performance.ko'), 'lease_seconds=5')
    loaded = True
    for index,mhz in enumerate((25,33,40,50,52,50)):
        (PARAM/'requested_mhz').write_text(str(mhz))
        sample()
        ios = Path('/sys/kernel/debug/mmc0/ios').read_text()
        print('EMMC_RATE_START', json.dumps({'requested_mhz':mhz,'ios':ios}), flush=True)
        logfile = ROOT/('io-'+str(index)+'-'+str(mhz)+'MHz.log')
        with logfile.open('w') as stream:
            child = subprocess.Popen([sys.executable, '-u', __file__, 'io-worker'], stdout=stream, stderr=subprocess.STDOUT)
            limit = time.monotonic()+65
            while child.poll() is None:
                sample()
                (PARAM/'requested_mhz').write_text(str(mhz))
                assert time.monotonic() < limit
                time.sleep(1)
            assert child.returncode == 0, logfile.read_text()
        output = logfile.read_text()
        transfers = json.loads(re.search(r'DIRECT_SCRATCH_IO_PASS (\[.*\])', output)[1])
        record = {'requested_mhz':mhz, 'ios':ios, 'transfers':transfers}
        records.append(record)
        print('EMMC_RATE_PASS', json.dumps(record), flush=True)
        (ROOT/'trial-state.json').write_text(json.dumps({'boot_id':BOOT,'records':records,'peaks_mc':peaks},indent=2)+'\n')
    # Verify the kernel's independent lease return without a userspace request.
    time.sleep(6)
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
    assert int((PARAM/'fault').read_text()) == 0
    run('rmmod', 'tzx_emmc_performance')
    loaded = False
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
    sample_errors = Path('/sys/kernel/debug/mmc0/err_stats').read_text()
    assert all(int(s) == 0 for s in re.findall(r':\s+(\d+)', sample_errors))
    audit = run('python3','/home/debian/verify_safe_memory.py','--files-only',timeout=100)
    assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
    (ROOT/'file-audit.log').write_text(audit)
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    outcome = {'status':'PASS','boot_id':BOOT,'records':records,'peaks_mc':peaks,
        'module_sha256':'8db02845e4630a11b711145cf5c4403d334416244807e519c85755d5a7a5a878',
        'lease_expiry_restores_25MHz':True,'unload_restores_25MHz':True,
        'mmc_errors':sample_errors,'mapped_files_audit':audit,
        'boot_areas_changed':False,'mode_voltage_buswidth_changed':False,
        'elapsed':round(time.monotonic()-started,2)}
finally:
    if child is not None and child.poll() is None:
        child.kill()
        child.wait(timeout=10)
    if loaded:
        try:
            (PARAM/'requested_mhz').write_text('25')
        finally:
            run('rmmod', 'tzx_emmc_performance')
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
    if FILE.exists():
        FILE.unlink()
    stop_ping.set()
    if ping is not None:
        ping.join(timeout=3)
    if watchdog is not None:
        os.write(watchdog,b'V')
        os.close(watchdog)
if outcome:
    (ROOT/'trial-result.json').write_text(json.dumps(outcome,indent=2)+'\n')
    print('EMMC_DDR52_PERFORMANCE_TRIAL_PASS', json.dumps(outcome), flush=True)
