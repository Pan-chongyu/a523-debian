"""Pause desktop audio for a boot rate check or bounded low-volume speaker test."""
import argparse
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--label', default='boot')
parser.add_argument('--tone', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
module = Path('/lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_codec_driver.ko')
assert hashlib.sha256(module.read_bytes()).hexdigest() == '013bcbe659aba5cae4d747c18fdce0c38b81ba782527bccab528f1de8132bf2d'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
prefix = ['sudo', '-u', 'debian', 'env', 'XDG_RUNTIME_DIR=/run/user/1000', 'systemctl', '--user']


def run(*command, timeout=35):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
for unit in ('pulseaudio.service', 'pulseaudio.socket'):
    assert run(*prefix, 'is-enabled', unit).strip() == 'enabled'
state = Path('/run/tzx-codec-rate-mixer-state')
assert not state.exists()
run('alsactl', '-f', str(state), 'store', 'A523')
run(*prefix, 'mask', '--runtime', 'pulseaudio.service', 'pulseaudio.socket')
try:
    run(*prefix, 'stop', 'pulseaudio.service', 'pulseaudio.socket')
    if args.tone:
        run('amixer', '-q', '-c', 'A523', 'cset', 'name=Master Playback Volume', '127,127')
        run('amixer', '-q', '-c', 'A523', 'cset', 'name=Master Playback Switch', '1,1')
        run('amixer', '-q', '-c', 'A523', 'cset', 'name=Lineout Playback Volume', '31')
        files = {}
        for rate, pitch in ((16000, 440), (48000, 660), (96000, 880)):
            samples = array('h')
            for frame in range(rate*8):
                # Soft 10 ms ramps, 300 ms tone in each second, both channels.
                phase = frame % rate / rate
                envelope = min(1, phase/.01, max(0, (.3-phase)/.01)) if phase < .3 else 0
                value = int(12000*envelope*math.sin(2*math.pi*pitch*frame/rate))
                samples.extend((value, value))
            path = Path('/run')/f'tzx-rate-tone-{rate}.raw'
            assert not path.exists()
            path.write_bytes(samples.tobytes())
            files[rate] = path
        try:
            print('CODEC_RATE_LOW_VOLUME_TONE_STARTED_72_SECONDS', flush=True)
            for cycle in range(3):
                for rate, path in files.items():
                    print('SPEAKER_TONE_RATE', rate, 'CYCLE', cycle+1, flush=True)
                    run('aplay', '-q', '-D', 'hw:A523,0', '--disable-resample', '-t', 'raw',
                        '-f', 'S16_LE', '-r', str(rate), '-c', '2', str(path), timeout=14)
        finally:
            for path in files.values():
                path.unlink()
    else:
        subprocess.run(['python3', '-u', '/home/debian/verify_codec_rates.py',
                        '--short', '--label', args.label], check=True, timeout=90)
finally:
    run('alsactl', '-f', str(state), 'restore', 'A523')
    state.unlink()
    run(*prefix, 'unmask', '--runtime', 'pulseaudio.service', 'pulseaudio.socket')
    run(*prefix, 'start', 'pulseaudio.socket', 'pulseaudio.service')
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert run('systemctl', '--failed', '--no-legend').strip() == ''
print('CODEC_INSTALLED_RATE_TEST_PULSE_AND_MIXER_RESTORED', json.dumps({'boot_id': BOOT, 'tone': args.tone}), flush=True)
