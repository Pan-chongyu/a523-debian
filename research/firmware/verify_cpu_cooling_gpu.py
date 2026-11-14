"""Verify service stop order, GPU suite and integrity with the real cooling zone."""
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0


def run(*command, timeout=80, **kwargs):
    return subprocess.run(command, check=True, timeout=timeout, **kwargs)


run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
run('systemctl', 'stop', 'tzx-cpufreq.service')
assert not Path('/sys/module/tzx_cpu_cooling').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert not list(Path('/sys/devices/system/cpu/cpufreq').glob('policy*'))
assert Path('/sys/module/panfrost').exists()
run('systemctl', 'start', 'tzx-cpufreq.service')
run('systemctl', 'start', 'tzx-cpu-cooling.service')
run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
print('CPU_COOLING_BINDS_TO_CPUFREQ_STOP_ORDER_AND_RESTART_PASS', flush=True)
run('python3', '-u', '/home/debian/verify_gpu_memory_pressure.py', '--memory-mib', '512',
    '--gpu-cycles', '1', '--backend', 'x11', '--log-prefix', 'gpu-cpu-cooling-production-v2',
    env=dict(os.environ, TZX_GPU_EXPECT_AWAKE='0', TZX_GPU_TRACE_SCENES='1'), timeout=250)
run('python3', '-u', '/home/debian/verify_safe_memory.py', '--files-only', timeout=150)
run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
print('CPU_COOLING_GPU_FILES_AND_LIFECYCLE_PASS', flush=True)
