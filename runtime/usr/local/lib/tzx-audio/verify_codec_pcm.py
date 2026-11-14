"""Run a bounded silent ALSA playback test after manual codec probe succeeds."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='/home/debian/codec-pcm-result.json')
args = parser.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-periph1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
assert Path('/proc/sys/kernel/panic_on_oops').read_text().strip() == '1'
assert Path('/proc/sys/kernel/panic').read_text().strip() == '5'
assert int(Path('/proc/sys/kernel/tainted').read_text()) & 128 == 0
assert Path('/sys/module/tzx_codec_driver').is_dir(), 'Load the guarded codec candidate first'
cards = Path('/proc/asound/cards').read_text()
matches = re.findall(r'^\s*(\d+)\s+\[([^]]+)\].*TZX', cards, re.MULTILINE)
assert len(matches) == 1, cards
card, card_id = matches[0]
counter_path = Path('/sys/bus/platform/devices/7110000.audio-codec/pcm_counters')
boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def counters():
    line = counter_path.read_text().strip()
    match = re.fullmatch(r'dac_samples=(\d+) adc_samples=(\d+) dac_fifo=([0-9a-f]+) adc_fifo=([0-9a-f]+)', line)
    assert match, line
    return dict(zip(('dac_samples', 'adc_samples', 'dac_fifo', 'adc_fifo'),
                    [int(match[1]), int(match[2]), int(match[3], 16), int(match[4], 16)]))


result = {'boot_id': boot_id, 'card': card, 'card_id': card_id.strip(),
          'before': counters(), 'sound_audibility_verified': False}
started = time.monotonic()
try:
    playback = subprocess.run(['aplay', '-D', f'hw:{card},0', '-t', 'raw',
                               '-f', 'S16_LE', '-r', '48000', '-c', '2',
                               '--duration=2', '/dev/zero'],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
    result.update(returncode=playback.returncode, output=playback.stdout.decode(errors='replace'))
except subprocess.TimeoutExpired as error:
    result.update(returncode=None, output=(error.stdout or b'').decode(errors='replace'), timed_out=True)
result['elapsed_seconds'] = round(time.monotonic() - started, 3)
result['after'] = counters()
result['kernel_tainted'] = int(Path('/proc/sys/kernel/tainted').read_text())
result['boot_unchanged'] = boot_id == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
# prepare() zeros the sample counter, so inspect the completed stream count.
# The hardware counter's channel aggregation is deliberately not assumed here.
result['pcm_dma_verified'] = (result['returncode'] == 0 and result['boot_unchanged']
    and not result['kernel_tainted'] & 128
    and not re.search(r'underrun|overrun|I/O error', result['output'], re.IGNORECASE)
    and 1.5 <= result['elapsed_seconds'] <= 6
    and result['after']['dac_samples'] >= 48000)
Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['pcm_dma_verified'] else 1)
