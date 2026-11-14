"""Qualify a manually loaded DMA32/MMU candidate across desktop and KMS."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/var/lib/tzx/gpu-qualified').exists()
parser = argparse.ArgumentParser()
parser.add_argument('--trial-id', default='desktop-final')
parser.add_argument('--log-prefix', default='gpu-dma32-mmu')
parser.add_argument('--aarch64-pgtable', action='store_true')
parser.add_argument('--keep-awake', action='store_true')
args = parser.parse_args()
assert args.trial_id and all(c.isalnum() or c == '-' for c in args.trial_id)
assert args.log_prefix and all(c.isalnum() or c in '-_' for c in args.log_prefix)


def run(*command, timeout=90, env=None):
    print('TRIAL_COMMAND', json.dumps(command), flush=True)
    subprocess.run(command, check=True, timeout=timeout, env=env)


loader = ['python3', '/home/debian/start_gpu_dma32_trial.py', '--mmu-init',
          '--trial-id', args.trial_id, '--restart-desktop-on-exit']
if args.aarch64_pgtable:
    loader.append('--aarch64-pgtable')
if args.keep_awake:
    loader.append('--keep-awake')
run(*loader, timeout=180)
contexts = ['python3', '/home/debian/verify_gpu_context_restarts.py', '--cycles', '4']
if args.keep_awake:
    contexts.append('--keep-awake')
run(*contexts, timeout=150)
override = Path('/run/systemd/system/lightdm.service.d/95-gpu-clockfix-test.conf')
override.parent.mkdir(parents=True, exist_ok=True)
override.write_text('[Service]\nExecStart=\nExecStart=/usr/sbin/lightdm '
                    '--config=/usr/local/lib/tzx-accel-gpu/lightdm.conf\n')
run('systemctl', 'daemon-reload')
run('systemctl', 'restart', 'lightdm')
environment = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
for attempt in range(25):
    result = subprocess.run(['glxinfo', '-B'], env=environment, capture_output=True,
                            text=True, timeout=8)
    if result.returncode == 0 and 'Mali-G57' in result.stdout and 'Accelerated: yes' in result.stdout:
        print(result.stdout, flush=True)
        break
    time.sleep(1)
else:
    raise RuntimeError('Accelerated Xorg did not become ready')
run('python3', '/home/debian/verify_gpu_memory_pressure.py', '--backend', 'x11',
    '--log-prefix', args.log_prefix + '-x11-final', '--memory-mib', '2560',
    '--gpu-cycles', '4', timeout=530)
print('GPU_DMA32_MMU_X11_COMBINED_MEMORY_PASS', flush=True)
# DRM master is released only for this explicit screen-presentation stage.
run('systemctl', 'stop', 'lightdm')
run('python3', '/home/debian/verify_gpu_clockfix.py', '--backend', 'drm',
    '--present', '--cycles', '2', '--log-prefix', args.log_prefix + '-present-final',
    timeout=440)
print('GPU_DMA32_MMU_DESKTOP_AND_NATIVE_PRESENT_QUALIFICATION_PASS', flush=True)
