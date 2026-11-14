"""systemd fallback even when the GPU performance supervisor is killed."""
from pathlib import Path
import subprocess

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
parameters = Path('/sys/module/tzx_gpu_performance/parameters')
if parameters.exists():
    (parameters/'requested_mhz').write_text('200')
    subprocess.run(['rmmod', 'tzx_gpu_performance'], check=True, timeout=15)
assert int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text()) == 200000000
Path('/var/lib/tzx/gpu-performance-pending.json').unlink(missing_ok=True)
print('GPU_PERFORMANCE_200_MHZ_RESTORED', flush=True)
