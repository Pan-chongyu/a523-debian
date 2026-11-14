"""Negative control: direct I/O and CPU memory pressure with the GPU unloaded."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
from tzx_direct_io import read_direct

parser = argparse.ArgumentParser()
parser.add_argument('--memory-mib', type=int, default=512)
parser.add_argument('--reader', action='store_true')
args = parser.parse_args()
assert 128 <= args.memory_mib <= 2560 and args.memory_mib % 8 == 0

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
if args.reader:
    files = [Path('/usr/bin/glmark2-es2-drm'), Path('/usr/bin/glmark2-es2'),
             Path('/usr/lib/aarch64-linux-gnu/libc.so.6')]
    files.extend(Path('/usr/lib/aarch64-linux-gnu').glob('libgallium-*.so'))
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    started = time.monotonic()
    count = 0
    while time.monotonic() - started < 70:
        assert not Path('/sys/module/panfrost').exists()
        for path, digest in hashes.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            read_direct(path, expected_sha256=digest)
        count += 1
        if count % 5 == 0:
            print('CPU_ONLY_DIRECT_IO_ITERATIONS', count, flush=True)
    print('CPU_ONLY_DIRECT_IO_INTEGRITY_PASS', count, flush=True)
    raise SystemExit(0)

reader = subprocess.Popen([sys.executable, __file__, '--reader'])
cpu = None
try:
    time.sleep(5)
    binary = Path('/home/debian/memory-check-bounded')
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == '2f7ea0da43c78531b035dc330c8ef51d9764155e21d592679850b8ba0087f4f5'
    for cycle in range(3):
        assert reader.poll() is None
        cpu = subprocess.Popen([str(binary), str(args.memory_mib)], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
        output = cpu.communicate(timeout=45)[0]
        print('CPU_ONLY_RAM_CYCLE', cycle + 1, output, flush=True)
        assert cpu.returncode == 0 and f'MEMORY_TEST_{args.memory_mib}_MIB_8_THREADS_PASS' in output
        time.sleep(3)
    assert reader.wait(timeout=90) == 0
    print('CPU_ONLY_DIRECT_IO_WITH_MEMORY_PRESSURE_PASS', flush=True)
finally:
    for process in (cpu, reader):
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
