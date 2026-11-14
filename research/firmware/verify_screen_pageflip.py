"""Validate real KMS page-flip events, then restore the existing desktop."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/module/tzx_display/parameters/screen_revision').read_text().strip() in ('screen-functions-2-vblank', 'screen-functions-3-doublebuffer', 'screen-functions-4-standby', 'screen-functions-5-poweron')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
brightness = Path('/sys/class/backlight/tzx-panel/brightness')
saved_brightness = brightness.read_text()
counter = Path('/sys/module/tzx_display/parameters/screen_vblank_events')
doublebuffer = Path('/sys/module/tzx_display/parameters/screen_buffer_commits')
commits_before = int(doublebuffer.read_text()) if doublebuffer.exists() else None


def run(*cmd, timeout=80):
    return subprocess.run(cmd, check=True, timeout=timeout)


info = subprocess.check_output(['modetest', '-M', 'tzx-a523', '-c', '-p'], text=True, timeout=12)
connector = re.search(r'^(\d+)\s+\d+\s+connected\s+DSI-1', info, re.M).group(1)
crtc = re.search(r'CRTCs:\n[^\n]+\n(\d+)\s', info).group(1)
tests = []
try:
    # Leave completed startup checks active: they require fresh loader markers.
    run('systemctl', 'stop', 'lightdm')
    for atomic in (False,):
        before = int(counter.read_text())
        cmd = ['stdbuf', '-oL', '-eL', 'modetest', '-M', 'tzx-a523', '-s', connector+'@'+crtc+':#0', '-v']
        if atomic:
            cmd.append('-a')
        log = Path('/home/debian/screen-pageflip-'+('atomic' if atomic else 'legacy')+'.log')
        with log.open('w') as output:
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
            try:
                time.sleep(12)
                assert process.poll() is None, log.read_text()
                process.stdin.write(b'\n')
                process.stdin.flush()
                process.wait(timeout=15)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        text = log.read_text()
        print(text, flush=True)
        assert process.returncode == 0, process.returncode
        assert not any(v in text.lower() for v in ('failed', 'error', 'timed out')), text
        frequencies = [float(v) for v in re.findall(r'freq:\s+([\d.]+)', text)]
        assert frequencies and all(60.0 < f < 64.5 for f in frequencies), text
        events = int(counter.read_text())-before
        assert 680 <= events <= 850, events
        tests.append({'atomic_modeset': atomic, 'frequencies_Hz': frequencies,
                      'hardware_irq_delta': events, 'log': str(log), 'result': 'PASS'})
finally:
    run('systemctl', 'start', 'lightdm')
    env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
    for attempt in range(30):
        ready = subprocess.run(['glxinfo', '-B'], env=env, capture_output=True, text=True, timeout=8)
        if ready.returncode == 0 and 'Mali-G57' in ready.stdout:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Accelerated desktop did not recover after the KMS test')
    brightness.write_text(saved_brightness)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
result = {'boot_id': boot, 'result': 'PASS', 'tests': tests, 'desktop_restored': True,
          'limitation': 'page-flip event timing verified; fixed scanout shadow copies can still tear'}
if doublebuffer.exists():
    assert int(Path('/sys/module/tzx_display/parameters/screen_buffer_errors').read_text()) == 0
    assert int(doublebuffer.read_text()) - commits_before > 300
    result['buffer_address_commits'] = int(doublebuffer.read_text()) - commits_before
    result['limitation'] = 'RCQ address latches and events verified; subjective moving-image inspection separate'
Path('/var/lib/tzx/screen-pageflip-test.json').write_text(json.dumps(result, indent=2)+'\n')
print('TZX_SCREEN_KMS_PAGEFLIP_EVENTS_PASS', json.dumps(result), flush=True)
