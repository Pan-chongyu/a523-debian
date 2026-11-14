"""Stop one explicit GPU scene run at a CPU signal and preserve its code page."""
import argparse
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--backend', choices=('x11', 'drm'), default='x11')
parser.add_argument('--tag', required=True)
parser.add_argument('--present', action='store_true')
parser.add_argument('--self-test', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert args.tag and all(c.isalnum() or c in '-_' for c in args.tag)
assert not args.present or args.backend == 'drm'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
directory = Path('/home/debian/tzx-gpu-debug')
directory.mkdir(mode=0o700, exist_ok=True)
batch = directory / (args.tag + '.gdb')
with batch.open('x', encoding='ascii') as stream:
    stream.write('''set pagination off
set confirm off
set debuginfod enabled off
set auto-load safe-path /nonexistent
set startup-with-shell off
set disable-randomization off
handle SIGPIPE nostop noprint pass
run
python
import gdb
if gdb.selected_inferior().pid:
    print('GPU_DEBUGGER_SIGNAL_STOP', flush=True)
    gdb.execute('info registers')
    gdb.execute('thread apply all bt 6')
    gdb.execute('x/12i $pc-16')
    try:
        exec(open('/home/debian/capture_gpu_stop.py').read())
    except BaseException as error:
        print('GPU_DEBUGGER_CAPTURE_ERROR', repr(error), flush=True)
    gdb.execute('quit 90')
else:
    code = int(gdb.parse_and_eval('$_exitcode'))
    print('GPU_DEBUGGER_NORMAL_EXIT', code, flush=True)
    gdb.execute('quit ' + str(0 if code == 0 else 91))
end
''')
if args.self_test:
    synthetic = directory / (args.tag + '-synthetic.py')
    with synthetic.open('x', encoding='ascii') as stream:
        stream.write('import os, signal\nos.kill(os.getpid(), signal.SIGILL)\n')
    command = ['/usr/bin/python3', str(synthetic)]
elif args.backend == 'x11':
    command = ['/usr/bin/glmark2-es2', '--size', '400x400', '--off-screen', '-b', ':duration=2']
else:
    command = ['/usr/bin/glmark2-es2-drm', '--winsys-options', 'drm-device=/dev/dri/card0',
               '--size', '400x400', '--off-screen', '-b', ':duration=2']
    if args.present:
        command.remove('--off-screen')
        command += ['--visual-config', 'red=8:green=8:blue=8:alpha=0:buffer=32:stencil=8']
environment = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
os.execvpe('/usr/bin/gdb', ['gdb', '--nx', '--nh', '--quiet', '--batch', '-x', str(batch),
                          '--args', '/usr/bin/stdbuf', '-oL', '-eL', *command], environment)
