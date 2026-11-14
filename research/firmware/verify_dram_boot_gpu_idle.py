"""Record actual idle transitions around repeated GPU shader contexts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
subprocess.run(['python3', '/home/debian/run_dram_boot_copy_trial.py', '--verify-only'], check=True, timeout=40)
module = Path('/home/debian/panfrost-dma32-aarch64.ko')
assert hashlib.sha256(module.read_bytes()).hexdigest() == 'ad4127adbd990361f89dfa65e3707927609f7eefedc766cd03dedb25f6ba97ae'
power = Path('/sys/bus/platform/devices/1800000.gpu/power')
try:
    subprocess.run(['modprobe', 'gpu_sched'], check=True, timeout=20)
    subprocess.run(['insmod', str(module), 'tzx_dma32=1'], check=True, timeout=20)
    subprocess.run(['modprobe', 'tzx_gpu_nodes'], check=True, timeout=20)
    assert Path('/dev/dri/renderD128').exists()
    assert (power/'control').read_text().strip() == 'auto'
    initial = int((power/'runtime_suspended_time').read_text())
    observations = []
    for cycle in range(8):
        until = time.monotonic()+3
        while (power/'runtime_status').read_text().strip() != 'suspended':
            assert time.monotonic() < until, 'GPU never reached idle suspend'
            time.sleep(0.05)
        before = int((power/'runtime_suspended_time').read_text())
        command = ['python3', '/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py',
                   '--node', '/dev/dri/by-path/platform-tzx-de-scanout-card']
        env = dict(os.environ)
        if cycle % 2 == 0:
            env['MESA_SHADER_CACHE_DISABLE'] = 'true'
        else:
            env.pop('MESA_SHADER_CACHE_DISABLE', None)
        result = subprocess.run(command, capture_output=True, text=True, timeout=18, env=env)
        print(result.stdout, flush=True)
        assert result.returncode == 0 and 'GPU_SHADER_AND_PIXEL_READBACK_PASS' in result.stdout
        time.sleep(0.3)
        after = int((power/'runtime_suspended_time').read_text())
        assert after > before
        row = {'cycle': cycle+1, 'before_status': 'suspended',
               'after_status': (power/'runtime_status').read_text().strip(),
               'suspended_ms_before': before, 'suspended_ms_after': after}
        observations.append(row)
        print('DRAM_BOOT_GPU_ACTUAL_IDLE_CONTEXT', json.dumps(row), flush=True)
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    faults = [row for row in subprocess.check_output(['dmesg'], text=True).splitlines()
              if 'panfrost' in row and any(s in row for s in ('fault', 'timeout'))]
    assert not faults, faults
    print('DRAM_BOOT_GPU_EIGHT_ACTUAL_IDLE_RESUME_PIXEL_TESTS_PASS',
          json.dumps({'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                      'observations': observations, 'initial_suspended_ms': initial}), flush=True)
finally:
    if Path('/sys/module/panfrost').exists():
        subprocess.run(['modprobe', '-r', 'panfrost'], check=True, timeout=25)
    assert not Path('/sys/module/panfrost').exists()
