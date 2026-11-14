"""Exact hardware PCM rate matrix; silent output, capture discarded immediately."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--label', default='manual')
parser.add_argument('--short', action='store_true')
args = parser.parse_args()
assert args.label and all(c.isalnum() or c == '-' for c in args.label)
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
COUNTERS = Path('/sys/bus/platform/devices/7110000.audio-codec/pcm_counters')
report = {'boot_id': BOOT, 'label': args.label, 'capture_saved': False, 'tests': []}
codes = {8000: 5, 12000: 4, 16000: 3, 24000: 2, 32000: 1, 48000: 0, 96000: 7}
children = []


def run(*command, timeout=30):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


def registers():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x07110000) as view:
            return {name: struct.unpack_from('<I', view, offset)[0]
                    for name, offset in (('dac_control', 0x10), ('adc_control', 0x30))}
    finally:
        os.close(fd)


def command(direction, rate, channels, seconds):
    return ['aplay' if direction == 'playback' else 'arecord', '-q', '-D', 'hw:A523,0',
            '--disable-resample', '-t', 'raw', '-f', 'S16_LE', '-r', str(rate),
            '-c', str(channels), '-d', str(seconds), '/dev/zero' if direction == 'playback' else '/dev/null']


def start(direction, rate, channels, seconds=2):
    process = subprocess.Popen(command(direction, rate, channels, seconds), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    children.append(process)
    status = Path('/proc/asound/card0')/('pcm0p' if direction == 'playback' else 'pcm0c')/'sub0'
    for attempt in range(40):
        assert process.poll() is None, process.communicate()
        hardware = (status/'hw_params').read_text()
        active = (status/'status').read_text()
        if 'state: RUNNING' in active:
            assert re.search(r'^rate: '+str(rate)+r' \('+str(rate)+r'/1\)$', hardware, re.M), hardware
            assert re.search(r'^channels: '+str(channels)+r'$', hardware, re.M), hardware
            assert 'format: S16_LE' in hardware, hardware
            regs = registers()
            field = regs['dac_control' if direction == 'playback' else 'adc_control']
            assert field >> 29 == codes[rate], (direction, rate, regs)
            clocks = [line.strip() for line in Path('/sys/kernel/debug/clk/clk_summary').read_text().splitlines()
                      if re.match(r'\s*audio-(dac|adc)\s', line)]
            assert len(clocks) == 2 and all('24576000' in line.split() for line in clocks), clocks
            return process, dict(direction=direction, rate=rate, channels=channels, seconds=seconds,
                                 hw_params=hardware, running_status=active, registers=regs, clocks=clocks)
        time.sleep(0.025)
    raise AssertionError('PCM never entered RUNNING')


def finish(process, entry, started):
    output, error = process.communicate(timeout=9)
    assert process.returncode == 0, (entry, output, error)
    assert not re.search(r'underrun|overrun|I/O error|not accurate', error, re.I), error
    counters = COUNTERS.read_text().strip()
    count = int(re.search(('dac' if entry['direction'] == 'playback' else 'adc')+r'_samples=(\d+)', counters)[1])
    expected = entry['rate']*entry['seconds']*(entry['channels'] if entry['direction'] == 'playback' else 1)
    # Hardware count is FIFO scalar samples, rather than ALSA interleaved frames.
    assert 0.90*expected <= count <= 1.15*expected+256, (entry, count, expected)
    elapsed = time.monotonic()-started
    assert entry['seconds']-0.3 <= elapsed <= entry['seconds']+4, elapsed
    entry.update(result='PASS', sample_counter=count, expected_scalar_samples=expected,
                 counters=counters, elapsed_seconds=round(elapsed, 3), stderr=error)
    report['tests'].append(entry)
    print('CODEC_EXACT_RATE_PCM_PASS', json.dumps(entry), flush=True)


run('amixer', '-q', '-c', 'A523', 'cset', 'name=ADDA Loop Mode', '0')
run('amixer', '-q', '-c', 'A523', 'cset', 'name=Master Playback Switch', '0,0')
try:
    rates = (8000, 16000, 48000) if args.short else (8000, 12000, 16000, 24000, 32000, 48000)
    for direction in ('playback', 'capture'):
        for rate in rates+((96000,) if direction == 'playback' else ()):
            started = time.monotonic()
            process, entry = start(direction, rate, 2 if direction == 'playback' else 1)
            finish(process, entry, started)
    if not args.short:
        started = time.monotonic()
        process, entry = start('playback', 16000, 1)
        finish(process, entry, started)
    # Different simultaneous rates verify independent DAC/ADC FIFO dividers.
    capture_started = time.monotonic()
    capture, capture_entry = start('capture', 16000, 1, seconds=3)
    play_started = time.monotonic()
    playback, play_entry = start('playback', 96000, 2, seconds=2)
    finish(playback, play_entry, play_started)
    finish(capture, capture_entry, capture_started)
    report['mixed_rate_duplex'] = '96k stereo playback + 16k mono capture PASS'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    report['result'] = 'PASS'
    path = Path('/var/lib/tzx')/('codec-rates-'+args.label+'.json')
    assert not path.exists()
    temporary = path.with_suffix('.new')
    with temporary.open('w') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fchmod(stream.fileno(), 0o600)
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
    print('CODEC_FIXED_CLOCK_EXACT_RATE_MATRIX_AND_MIXED_DUPLEX_PASS', json.dumps({
        'boot_id': BOOT, 'tests': len(report['tests']), 'capture_saved': False}), flush=True)
finally:
    for process in children:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
