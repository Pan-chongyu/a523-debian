"""Exercise the BSP-defined internal DAC-to-ADC loop; keep lineout muted."""
import array
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/proc/sys/kernel/panic_on_oops').read_text().strip() == '1'
assert int(Path('/proc/sys/kernel/tainted').read_text()) & 128 == 0
assert Path('/sys/module/tzx_codec_driver').is_dir()


def control(name, value):
    subprocess.run(['amixer', '-q', '-c', '0', 'cset', 'name=' + name, value], check=True)


pcm = array.array('h')
for i in range(96000):
    pcm.extend((int(4096 * math.sin(2 * math.pi * 1000 * i / 48000)),
                int(4096 * math.sin(2 * math.pi * 1500 * i / 48000))))
result = {}
control('Master Playback Switch', '0,0')
control('Lineout Playback Volume', '0')
control('ADC1 Capture Volume', '159')
control('ADDA Loop Mode', '1')
try:
    with tempfile.TemporaryFile() as recording:
        capture = subprocess.Popen(['arecord', '-q', '-D', 'hw:0,0', '-t', 'raw', '-f', 'S16_LE',
                                    '-r', '48000', '-c', '1', '-d', '3', '-'],
                                   stdout=recording, stderr=subprocess.PIPE)
        try:
            time.sleep(0.45)
            playback = subprocess.run(['aplay', '-q', '-D', 'hw:0,0', '-t', 'raw', '-f', 'S16_LE',
                                       '-r', '48000', '-c', '2', '-'], input=pcm.tobytes(),
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=6)
            _, errors = capture.communicate(timeout=6)
        finally:
            if capture.poll() is None:
                capture.kill()
                capture.communicate()
        recording.seek(0)
        samples = array.array('h', recording.read())
    middle = samples[48000:96000]
    mean = sum(middle) / len(middle)
    centered = [v - mean for v in middle]
    result = {'samples': len(samples), 'unique_values': len(set(samples)),
              'minimum': min(samples), 'maximum': max(samples),
              'ac_rms': math.sqrt(sum(v*v for v in centered) / len(centered)),
              'capture_returncode': capture.returncode,
              'capture_stderr': errors.decode(errors='replace'),
              'playback_returncode': playback.returncode,
              'playback_output': playback.stdout.decode(errors='replace')}
    for frequency in (1000, 1500):
        real = sum(v * math.cos(2*math.pi*frequency*i/48000) for i,v in enumerate(centered))
        imaginary = sum(v * math.sin(2*math.pi*frequency*i/48000) for i,v in enumerate(centered))
        result[f'tone_{frequency}_amplitude'] = 2 * math.hypot(real, imaginary) / len(centered)
finally:
    control('ADDA Loop Mode', '0')
    control('ADC1 Capture Volume', '127')
    control('Master Playback Switch', '0,0')
result['kernel_tainted'] = int(Path('/proc/sys/kernel/tainted').read_text())
result['internal_loop_verified'] = (result['playback_returncode'] == 0
    and result['capture_returncode'] == 0 and result['tone_1000_amplitude'] > 10
    and not result['kernel_tainted'] & 128)
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['internal_loop_verified'] else 1)
