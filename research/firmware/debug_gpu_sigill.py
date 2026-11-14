"""Capture the failing CPU instruction during a bounded native DRM trial."""
import hashlib
import argparse
import os
from pathlib import Path
import signal
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert hashlib.sha256(Path('/lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_display.ko').read_bytes()).hexdigest() == 'a00991fbcf52fd9624fb62b708e108ad22edf30546c84d3a5bffa65cc7a2a27f'
assert Path('/usr/bin/gdb').exists()
parser = argparse.ArgumentParser()
parser.add_argument('--tag', default='gdb')
args = parser.parse_args()
assert args.tag and all(c.isalnum() or c in '-_' for c in args.tag)
directory = Path('/home/debian/tzx-gpu-debug')
directory.mkdir(mode=0o700, exist_ok=True)
batch = directory/'commands.gdb'
batch.write_text(r'''set pagination off
set confirm off
set debuginfod enabled off
set auto-load safe-path /nonexistent
run
echo \n=== STOPPED GPU TEST ===\n
thread apply all bt 10
info registers
x/16i $pc-24
python exec(open('/home/debian/capture_gpu_stop.py').read())
info proc mappings
quit
''')
zones = list(Path('/sys/class/thermal').glob('thermal_zone*'))
assert len(zones) == 5

def faults():
    return [line for line in subprocess.check_output(['dmesg'], text=True).splitlines()
            if 'panfrost' in line and ('fault' in line or 'timeout' in line)]

assert not faults()
deadline = time.monotonic()+210
for attempt in range(2):
    log = directory/(args.tag+'-'+str(attempt+1)+'.log')
    command = ['gdb', '--quiet', '--batch', '-x', str(batch), '--args',
               '/usr/bin/glmark2-es2-drm', '--winsys-options', 'drm-device=/dev/dri/card0',
               '--visual-config', 'red=8:green=8:blue=8:alpha=0:buffer=32:stencil=8',
               '-b', ':duration=2']
    with log.open('w') as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            while process.poll() is None:
                values = {p.joinpath('type').read_text().strip(): int(p.joinpath('temp').read_text()) for p in zones}
                assert all(0 < value < 75000 for value in values.values()), 'Temperature guard'
                assert time.monotonic() < deadline, 'Debugger deadline'
                assert not faults(), 'New GPU fault'
                print('GPU_DEBUG_PROGRESS', attempt+1, values, flush=True)
                time.sleep(3)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    result = log.read_text()
    print(result, flush=True)
    if 'received signal SIG' in result or 'terminated with signal SIG' in result:
        print('GPU_CPU_EXCEPTION_CAPTURED', str(log), flush=True)
        break
    assert 'exited normally' in result, ('Unexpected debugger result', str(log))
print('GPU_DEBUG_TRIAL_ENDED', flush=True)
