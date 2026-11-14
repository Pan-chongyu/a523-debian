"""Run full GPU scenes with bounded concurrent CPU RAM checks."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--memory-mib', type=int, default=512)
parser.add_argument('--gpu-cycles', type=int, default=4)
parser.add_argument('--backend', choices=['drm', 'x11'], default='drm')
parser.add_argument('--log-prefix', default='gpu-dma32-mmu-drm-pressure')
args = parser.parse_args()
assert 128 <= args.memory_mib <= 2560 and args.memory_mib % 8 == 0
assert 1 <= args.gpu_cycles <= 20
assert args.log_prefix and all(c.isalnum() or c in '-_' for c in args.log_prefix)

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
binary = Path('/home/debian/memory-check-bounded')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '2f7ea0da43c78531b035dc330c8ef51d9764155e21d592679850b8ba0087f4f5'
assert Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() == 'Y'
gpu = subprocess.Popen(['python3', '/home/debian/verify_gpu_clockfix.py',
                        '--backend', args.backend, '--cycles', str(args.gpu_cycles),
                        '--log-prefix', args.log_prefix])
cpu = None
try:
    time.sleep(12)
    for cycle in range(3):
        assert gpu.poll() is None, ('GPU workload ended before pressure test', gpu.returncode)
        cpu = subprocess.Popen([str(binary), str(args.memory_mib)], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
        started = time.monotonic()
        while cpu.poll() is None:
            assert gpu.poll() is None, ('GPU workload stopped during CPU pressure', gpu.returncode)
            assert time.monotonic() - started < 45, 'CPU RAM workload deadline'
            time.sleep(0.5)
        output = cpu.communicate()[0]
        print('GPU_CONCURRENT_CPU_RAM_CYCLE', cycle + 1, output, flush=True)
        assert cpu.returncode == 0 and f'MEMORY_TEST_{args.memory_mib}_MIB_8_THREADS_PASS' in output
        time.sleep(3)
    assert gpu.wait(timeout=args.gpu_cycles * 220) == 0
    print(f'GPU_FULL_{args.backend.upper()}_WITH_{args.gpu_cycles}_SCENES_AND_THREE_{args.memory_mib}MIB_CPU_MEMORY_PASSES', flush=True)
finally:
    for process in (cpu, gpu):
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
