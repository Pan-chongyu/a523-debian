"""Verify corrected CCU register and bounded GPU scenes with RAM/cache guards."""
import argparse
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import threading
import time
from tzx_direct_io import read_direct

parser=argparse.ArgumentParser()
parser.add_argument('--backend',choices=['x11','drm'],default='x11')
parser.add_argument('--log-prefix', default=None)
parser.add_argument('--present', action='store_true')
parser.add_argument('--cycles', type=int, default=2)
args=parser.parse_args()
trace_scenes = os.environ.get('TZX_GPU_TRACE_SCENES', '0') == '1'
expect_awake = os.environ.get('TZX_GPU_EXPECT_AWAKE', '0') == '1'
debug_stops = os.environ.get('TZX_GPU_DEBUG_STOPS', '0') == '1'
gpu_power = Path('/sys/bus/platform/devices/1800000.gpu/power')
initial_suspended_ms = None
if expect_awake:
    assert (gpu_power / 'control').read_text().strip() == 'on'
    assert (gpu_power / 'runtime_status').read_text().strip() == 'active'
    initial_suspended_ms = int((gpu_power / 'runtime_suspended_time').read_text())
assert not args.present or args.backend == 'drm'
assert 1 <= args.cycles <= 20
prefix=args.log_prefix or 'gpu-clockfix-'+args.backend
assert prefix and all(c.isalnum() or c in '-_' for c in prefix)
assert os.geteuid() == 0
assert any(build in os.uname().version for build in ('#3 ', '#4 ', '#5 ', '#6 '))
if '#6 ' in os.uname().version:
    assert hashlib.sha256(Path('/boot/config-7.3.3-tzx-a523-accel1').read_bytes()).hexdigest() == '8eb3abbbfc1ad05214d65cd63ac7ec145398782c3e858d20095d5f24ae660972'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
with mmap.mmap(fd, 4096, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ, offset=0x02001000) as registers:
    reg = struct.unpack_from('<I', registers, 0x670)[0]
os.close(fd)
print('GPU_CLK_REG', hex(reg), 'source_mux', (reg>>24)&7, 'masked_cycles', reg&15, flush=True)
assert (reg>>24)&7 == 5 and reg&15 == 0, 'Expected undivided fixed periph0-200M'
critical = [Path('/usr/lib/aarch64-linux-gnu')/name for name in
    ['libmount.so.1.1.0', 'libc.so.6', 'libsystemd.so.0.41.0', 'libgbm.so.1.0.0',
     'libEGL.so.1.1.0', 'libpcre2-8.so.0.14.0']]
critical = [p for p in critical if p.is_file()]
critical.extend(Path('/usr/lib/aarch64-linux-gnu').glob('libgallium-*.so'))
critical.extend(p for p in (Path('/usr/bin/glmark2-es2'), Path('/usr/bin/glmark2-es2-drm'))
                if p.is_file())
hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in critical}
def cache_check():
    for p, digest in hashes.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, ('CACHE_CHANGED', str(p))
        read_direct(p, expected_sha256=digest)
cache_check()
# Keep a separate allocation alive while the GPU allocates and retires buffers.
sentinel = os.urandom(32*1024*1024)
sentinel_hash = hashlib.sha256(sentinel).digest()
# Keep this trial's random bytes to identify a potential stale write from a
# previous owner if an unrelated page changes during GPU buffer retirement.
sentinel_path = Path('/home/debian/'+prefix+'-sentinel.bin')
with sentinel_path.open('xb') as stream:
    stream.write(sentinel)
    stream.flush()
    os.fsync(stream.fileno())
print('RAM_SENTINEL_FILE',str(sentinel_path),sentinel_hash.hex(),flush=True)
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096

def sentinel_check():
    if hashlib.sha256(sentinel).digest() == sentinel_hash:
        return
    original = sentinel_path.read_bytes()
    assert hashlib.sha256(original).digest() == sentinel_hash, 'Sentinel disk/cache also changed'
    pointer = ctypes.pythonapi.PyBytes_AsString
    pointer.argtypes = [ctypes.py_object]
    pointer.restype = ctypes.c_void_p
    address = pointer(sentinel)
    pages = []
    with open('/proc/self/pagemap', 'rb', buffering=0) as pagemap:
        for offset in range(0, len(sentinel), 4096):
            actual, expected = sentinel[offset:offset+4096], original[offset:offset+4096]
            if actual == expected:
                continue
            delta = [i for i, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]]
            pagemap.seek(((address+offset+delta[0])//4096)*8)
            entry = struct.unpack('<Q',pagemap.read(8))[0]
            pages.append({'data_offset': offset,'first':delta[0],'last':delta[-1],
                          'different_bytes':len(delta),'physical_page':hex((entry&((1<<55)-1))*4096),
                          'sample':actual[delta[0]:delta[0]+64].hex()})
    with Path(str(sentinel_path)+'.corrupt').open('xb') as stream:
        stream.write(sentinel); stream.flush(); os.fsync(stream.fileno())
    report={'expected_sha256':sentinel_hash.hex(),'actual_sha256':hashlib.sha256(sentinel).hexdigest(),
            'data_virtual_address':hex(address),'pages':pages}
    Path(str(sentinel_path)+'.json').write_text(json.dumps(report,indent=2)+'\n')
    print('RAM_SENTINEL_CORRUPTION_CAPTURE',json.dumps(report),flush=True)
    raise AssertionError('RAM sentinel changed; current bytes and PFNs saved')
def faults():
    return [row for row in subprocess.check_output(['dmesg'], text=True).splitlines()
        if 'panfrost' in row and any(word in row for word in ['fault', 'timeout'])]
before = faults()
assert not before, before
zones = list(Path('/sys/class/thermal').glob('thermal_zone*'))
zone_types = {p.joinpath('type').read_text().strip() for p in zones}
physical_zone_types = {'gpu-thermal', 'cpu-big-thermal', 'cpu-little-thermal', 'npu-thermal', 'ddr-thermal'}
assert physical_zone_types <= zone_types <= physical_zone_types | {'tzx-board-thermal'}
command = ['runuser','-u','debian','--','env','DISPLAY=:0',
    'XAUTHORITY=/home/debian/.Xauthority','stdbuf','-oL','-eL','glmark2-es2',
    '--size','400x400','--off-screen','-b',':duration=2']
if args.backend == 'drm':
    command=['glmark2-es2-drm','--winsys-options','drm-device=/dev/dri/card0','--size','400x400','--off-screen','-b',':duration=2']
    if args.present:
        command.remove('--off-screen')
        command += ['--visual-config','red=8:green=8:blue=8:alpha=0:buffer=32:stencil=8']
    command=['stdbuf','-oL','-eL']+command
peaks = {}
for cycle in range(args.cycles):
    log = Path('/home/debian/'+prefix+'-scenes-'+str(cycle+1)+'.log')
    started = time.monotonic()
    scene_command = command
    if debug_stops:
        scene_command = ['python3', '/home/debian/run_gpu_scene_debugger.py',
                         '--backend', args.backend, '--tag', prefix + '-debug-' + str(cycle + 1)]
        if args.present:
            scene_command.append('--present')
    with log.open('w') as output:
        process = subprocess.Popen(scene_command, stdout=subprocess.PIPE if trace_scenes else output,
                                   stderr=subprocess.STDOUT, text=trace_scenes,
                                   bufsize=1 if trace_scenes else -1)
        trace_errors = []
        reader = None
        if trace_scenes:
            def relay():
                try:
                    for line in process.stdout:
                        output.write(line)
                        output.flush()
                        print('GPU_SCENE_LIVE', cycle + 1, line.rstrip(), flush=True)
                except BaseException as error:
                    trace_errors.append(repr(error))
            reader = threading.Thread(target=relay, daemon=True)
            reader.start()
        try:
            while process.poll() is None:
                if expect_awake:
                    assert (gpu_power / 'control').read_text().strip() == 'on'
                    assert (gpu_power / 'runtime_status').read_text().strip() == 'active'
                    assert int((gpu_power / 'runtime_suspended_time').read_text()) == initial_suspended_ms
                values = {p.joinpath('type').read_text().strip(): int(p.joinpath('temp').read_text()) for p in zones}
                for key,value in values.items():
                    peaks[key] = max(peaks.get(key,value),value)
                assert all(0 < t < 75000 for t in values.values()), 'Temperature guard'
                assert time.monotonic()-started < 220, 'Workload deadline'
                assert faults() == before, 'New GPU fault'
                assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096, 'New kernel warning/oops'
                if args.present:
                    with log.open('rb') as observed:
                        observed.seek(max(0, log.stat().st_size-65536))
                        assert b'Error:' not in observed.read(), 'DRM presentation error'
                sentinel_check()
                cache_check()
                print(json.dumps({'cycle':cycle+1,'second':round(time.monotonic()-started,2),'temperatures_mC':values,'ram_cache_guard':'PASS'}),flush=True)
                time.sleep(3)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            if reader is not None:
                reader.join(timeout=5)
                assert not reader.is_alive() and not trace_errors, trace_errors
    text = log.read_text()
    print(text, flush=True)
    assert process.returncode == 0, process.returncode
    assert 'Mali-G57 (Panfrost)' in text and 'glmark2 Score:' in text
    if args.present:
        assert 'Error:' not in text, 'DRM presentation error'
cache_check()
sentinel_check()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert faults() == before
print('GPU_CLOCKFIX_TWO_FULL_SCENE_PASSES' if args.cycles == 2 else
      'GPU_CLOCKFIX_FULL_SCENE_PASSES_'+str(args.cycles), json.dumps(peaks), flush=True)
if expect_awake:
    assert int((gpu_power / 'runtime_suspended_time').read_text()) == initial_suspended_ms
    print('GPU_RUNTIME_SUSPENDED_TIME_UNCHANGED_MS', initial_suspended_ms, flush=True)
