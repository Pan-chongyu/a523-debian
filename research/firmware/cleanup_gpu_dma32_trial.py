"""End a GPU trial without restarting the current desktop by default."""
import argparse
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--restart-desktop', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'


def run(*command, check=True):
    return subprocess.run(command, check=check, timeout=45)


for name in ('/run/systemd/system/lightdm.service.d/95-gpu-clockfix-test.conf',
             '/run/systemd/system/tzx-display.service.d/98-dma32-test.conf'):
    Path(name).unlink(missing_ok=True)
run('systemctl', 'daemon-reload')
timers = subprocess.check_output(
    ['systemctl', 'list-units', '--all', '--type=timer', '--no-legend', '--plain'],
    text=True)
for line in timers.splitlines():
    name = line.split()[0]
    if name.startswith('tzx-dma32-independent-rollback') and name.endswith('.timer'):
        run('systemctl', 'stop', name)

if args.restart_desktop:
    run('systemctl', 'stop', 'lightdm')
if Path('/sys/module/panfrost').exists():
    # An active GPU desktop holds module references. Keep that session until
    # reboot unless a desktop restart was explicitly requested.
    run('modprobe', '-r', 'panfrost', check=args.restart_desktop)
if args.restart_desktop:
    run('systemctl', 'stop', 'tzx-display')
    run('systemctl', 'start', 'tzx-display')
    run('systemctl', 'start', 'lightdm')
os.sync()
state = {'desktop_restarted': args.restart_desktop,
         'gpu_still_loaded': Path('/sys/module/panfrost').exists(),
         'persistent_gpu_qualified': Path('/var/lib/tzx/gpu-qualified').exists(),
         'display_baseline_reload': 'completed' if args.restart_desktop else 'deferred_to_reboot'}
Path('/run/tzx-dma32-cleanup.json').write_text(json.dumps(state, indent=2) + '\n')
print('DMA32_TRIAL_CLEANUP', json.dumps(state), flush=True)
