"""Exercise notification and dependency failure on temporary, hardware-free units."""
import os
from pathlib import Path
import subprocess
import sys
import time

if sys.argv[1:2] == ['--worker']:
    subprocess.run(['systemd-notify', '--ready', '--status=probe-ready'], check=True)
    time.sleep(1.5)
    raise SystemExit(int(sys.argv[2]))
assert os.geteuid() == 0 and sys.argv[1:] == []
worker = str(Path(__file__).resolve())
def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True, timeout=12)
def props(name):
    return dict(v.split('=', 1) for v in run('systemctl', 'show', name,
        '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result').stdout.splitlines())
names = ['tzx-notify-lifecycle-probe.service', 'tzx-notify-bound-probe.service']
for exit_code in (0, 7):
    try:
        t = time.monotonic()
        run('systemd-run', '--unit='+names[0], '--property=Type=notify',
            '--property=NotifyAccess=all', '--property=RemainAfterExit=yes',
            '/usr/bin/python3', worker, '--worker', str(exit_code))
        assert time.monotonic()-t < 1.4
        run('systemd-run', '--unit='+names[1], '--property=BindsTo='+names[0],
            '--property=After='+names[0], '/usr/bin/sleep', '20')
        time.sleep(2)
        a, b = props(names[0]), props(names[1])
        if exit_code == 0:
            assert a['ActiveState']=='active' and a['SubState']=='exited' and b['ActiveState']=='active', (a,b)
        else:
            assert a['ActiveState']=='failed' and b['ActiveState']=='inactive', (a,b)
        print('NOTIFY_REMAIN_AFTER_EXIT_AND_FAILURE_PROPAGATION_PASS', exit_code, a, b, flush=True)
    finally:
        for name in names[::-1]:
            run('systemctl', 'stop', name, check=False)
            run('systemctl', 'reset-failed', name, check=False)
assert not run('systemctl','--failed','--no-legend','--plain').stdout.strip()
