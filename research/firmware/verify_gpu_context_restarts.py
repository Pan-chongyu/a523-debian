"""Exercise idle/resume and repeated EGL contexts with cached/uncached shaders."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--cycles', type=int, default=8)
parser.add_argument('--keep-awake', action='store_true')
args = parser.parse_args()
assert 1 <= args.cycles <= 30 and os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() == 'Y'
sentinel = os.urandom(32 * 1024 * 1024)
digest = hashlib.sha256(sentinel).digest()
zones = list(Path('/sys/class/thermal').glob('thermal_zone*'))
assert len(zones) == 5

def guard():
    if args.keep_awake:
        power = Path('/sys/bus/platform/devices/1800000.gpu/power')
        assert (power / 'control').read_text().strip() == 'on'
        assert (power / 'runtime_status').read_text().strip() == 'active'
    assert hashlib.sha256(sentinel).digest() == digest, 'RAM sentinel changed'
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    failures = [line for line in subprocess.check_output(['dmesg'], text=True).splitlines()
                if 'panfrost' in line and any(word in line for word in ('fault', 'timeout'))]
    assert not failures, failures
    values = {p.joinpath('type').read_text().strip(): int(p.joinpath('temp').read_text())
              for p in zones}
    assert all(0 < value < 75000 for value in values.values()), values
    return values

guard()
for cycle in range(args.cycles):
    for cache in ('disabled', 'enabled'):
        print('GPU_CONTEXT_BEGIN', cycle + 1, cache, flush=True)
        environment = dict(os.environ)
        if cache == 'disabled':
            environment['MESA_SHADER_CACHE_DISABLE'] = 'true'
        else:
            environment.pop('MESA_SHADER_CACHE_DISABLE', None)
        result = subprocess.run(
            ['python3', '/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py',
             '--node', '/dev/dri/by-path/platform-tzx-de-scanout-card'],
            env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=18)
        print(json.dumps({'cycle': cycle + 1, 'shader_cache': cache,
                          'returncode': result.returncode, 'output': result.stdout},
                         ensure_ascii=False), flush=True)
        print('GPU_CONTEXT_GUARD', json.dumps(guard()), flush=True)
        assert result.returncode == 0, result.stdout
        assert 'GPU_SHADER_AND_PIXEL_READBACK_PASS' in result.stdout
        # Exceed the 50ms idle delay before the next EGL context.
        time.sleep(0.25)
print('GPU_CONTEXT_RESTARTS_WITHOUT_RUNTIME_SUSPEND_PASS' if args.keep_awake else
      'GPU_CONTEXT_RESTARTS_AND_IDLE_RESUME_PASS', args.cycles * 2, flush=True)
