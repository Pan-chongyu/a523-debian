"""Read panel status/defaults while the guarded diagnostic owns DSI1.

Requires the exact tablet and a held diagnostic. Video status reads pause at
a frame boundary and restore the running video afterward. Standard command
tests preserve panel voltage/gamma/GIP settings and require timed cleanup.
"""
import fcntl
import json
import mmap
import os
from pathlib import Path
import struct
import sys
import time
import subprocess

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
action = sys.argv[1] if len(sys.argv) > 1 else 'status'
assert action in ('status', 'dump', 'standard', 'formats', 'long', 'ack', 'factory-wake', 'clock-wake', 'video-status')
video_status = action == 'video-status'
parameters = Path('/sys/module/tzx_dsi_probe/parameters')
assert (parameters / 'hold').read_text().strip() == 'Y'
assert (parameters / 'probe_panel').read_text().strip() == 'Y'
assert (parameters / 'vc').read_text().strip() == '0'
if (parameters / 'video').exists():
    assert (parameters / 'video').read_text().strip() == ('Y' if video_status else 'N')
if video_status:
    assert subprocess.run(['systemctl', 'is-active', '--quiet',
                           'tzx-display-test-timeout.timer']).returncode == 0
pattern_arg = sys.argv[2] if video_status and len(sys.argv) > 2 and sys.argv[2].startswith('pattern:') else None
test_pattern = int(pattern_arg.split(':')[1]) if pattern_arg else None
assert test_pattern is None or test_pattern in (1, 2, 3, 4, 5, 7)
test_color = int(sys.argv[2], 16) if video_status and len(sys.argv) > 2 and pattern_arg is None else None
assert test_color is None or 0 <= test_color <= 0xffffff
lock = open('/run/tzx-dsi-live.lock', 'w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
host = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x05508000)

def get(offset):
    return struct.unpack_from('<I', host, offset)[0]

def put(offset, value):
    struct.pack_into('<I', host, offset, value)

def packet(kind, data, receive=False):
    header = kind | (data << 8)
    masks = (0xf12cb7, 0xf2555b, 0x749a6d, 0xb8e38e, 0xdf03f0, 0xeffc00)
    ecc = sum(((header & mask).bit_count() & 1) << i for i, mask in enumerate(masks))
    put(0x200, (1 << 26) | (1 << 25) | (1 << 9))
    put(0x300, header | (ecc << 24))
    put(0x200, 3)
    put(0x48, (4 | (7 << 16) | (1 << 28) | (15 << 4)) if receive else (4 | (15 << 16)))
    put(0x10, 3 << 16)
    put(0x10, (3 << 16) | 1)
    deadline = time.monotonic() + 0.04
    while get(0x10) & 1:
        if time.monotonic() > deadline:
            put(0x10, 3 << 16)
            raise TimeoutError('LP instruction timeout')
        time.sleep(0.0001)

def read(command):
    packet(0x37, 8)
    packet(0x06, command, True)
    ctl = get(0x200)
    raw = bytes(host[0x240:0x260])
    kind = raw[0] & 0x3f
    if ctl & (1 << 26):
        raise OSError('RX overflow')
    if kind == 0x21:
        return raw[1:2]
    if kind == 0x22:
        return raw[1:3]
    if kind == 0x1c:
        n = int.from_bytes(raw[1:3], 'little')
        assert 0 < n <= 8 and ((ctl >> 16) & 31) + 1 >= n + 6
        return raw[4:4+n]
    raise OSError(f'RX header {raw[:4].hex()}, ctl={ctl:08x}')

def write1(command, value):
    packet(0x15, command | (value << 8))

def long_write(payload):
    """Standard DCS long write, with software ECC and payload CRC16."""
    assert 1 <= len(payload) <= 32
    header = 0x39 | (len(payload) << 8)
    masks = (0xf12cb7, 0xf2555b, 0x749a6d, 0xb8e38e, 0xdf03f0, 0xeffc00)
    ecc = sum(((header & mask).bit_count() & 1) << i for i, mask in enumerate(masks))
    crc = 0xffff
    for value in payload:
        for bit in range(8):
            crc = (crc >> 1) ^ (0x8408 if ((crc ^ (value >> bit)) & 1) else 0)
    data = struct.pack('<I', header | (ecc << 24)) + payload + struct.pack('<H', crc)
    put(0x200, (1 << 26) | (1 << 25) | (1 << 9))
    host[0x300:0x300 + len(data)] = data
    put(0x200, len(data) - 1)
    put(0x48, 4 | (15 << 16))
    put(0x10, 3 << 16)
    put(0x10, (3 << 16) | 1)
    deadline = time.monotonic() + 0.04
    while get(0x10) & 1:
        if time.monotonic() > deadline:
            put(0x10, 3 << 16)
            raise TimeoutError('long LP instruction timeout')
        time.sleep(0.0001)

def status():
    return {f'{command:02x}': read(command).hex() for command in range(0x0a, 0x10)}

def unlock():
    for command, value in ((0xe0, 0), (0xe1, 0x93), (0xe2, 0x65), (0xe3, 0xf8)):
        write1(command, value)

saved_video_mode = get(0x14)
saved_video_jump = get(0x48)
saved_video_cfg = get(0x4c)
if video_status:
    if test_pattern is not None:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                       offset=0x05502000) as tcon:
            value = struct.unpack_from('<I', tcon, 0x40)[0]
            struct.pack_into('<I', tcon, 0x40, (value & ~7) | test_pattern)
        put(0x2f8, 0xff)
        put(0x2f0, 2)
        time.sleep(0.2)
        print(json.dumps({'phase': 'running-tcon-pattern', 'pattern': test_pattern,
                          'inst': f'{get(0x2f0):08x}',
                          'fifo_underflow': f'{get(0xfc):08x}'}), flush=True)
    if test_color is not None:
        put(0x2f8, (1 << 28) | test_color)
        # The BSP documents the transfer-fast flag as write-one-to-clear.
        put(0x2f0, 2)
        time.sleep(0.2)
        print(json.dumps({'phase': 'running-test-color', 'rgb': f'{test_color:06x}',
                          'line': get(0x2e0), 'inst': f'{get(0x2f0):08x}',
                          'fifo_underflow': f'{get(0xfc):08x}'}), flush=True)
    # BSP dsi_close exits at the next NOP via HSCEXIT. Aborting HSD in
    # the middle of a packet can leave the PHY unable to send LP commands.
    put(0x4c, saved_video_cfg | (1 << 28))
    deadline = time.monotonic() + 0.06
    while get(0x10) & 1:
        if time.monotonic() > deadline:
            raise TimeoutError('video frame-boundary exit timeout')
        time.sleep(0.0001)
    print(json.dumps({'phase': 'video-frame-boundary-exit',
                      'inst': f'{get(0x2f0):08x}'}), flush=True)
    put(0x10, 3 << 16)
    time.sleep(0.001)
    put(0x4c, 0)
    put(0x14, 0)
    put(0x20, 0x1f)

try:
    identity = read(0x04).hex()
    assert identity == '936504', identity
    result = {'panel_id': identity, 'time': time.time(), 'pages': {}}
    if action == 'dump':
        unlock()
        # Page 0 includes write-only DCS opcodes, which are not meaningful
        # register reads. Only inspect vendor register pages here.
        for page in (1, 2, 3, 4):
            write1(0xe0, page)
            values = {}
            for command in range(0xe0):
                try:
                    values[f'{command:02x}'] = read(command).hex()
                except (TimeoutError, OSError) as error:
                    values[f'{command:02x}'] = {'error': str(error)}
            result['pages'][str(page)] = values
            print('DUMPED_PAGE', page, flush=True)
        Path('/home/debian/panel-default-registers.json').write_text(json.dumps(result, indent=2) + '\n')
        print('PANEL_DEFAULTS_SAVED', identity, len(result['pages']))
    elif action == 'factory-wake':
        assert (parameters / 'wake_panel').read_text().strip() == 'N'
        assert (parameters / 'dump_regs').read_text().strip() == 'N'
        assert subprocess.run(['systemctl', 'is-active', '--quiet',
                               'tzx-display-test-timeout.timer']).returncode == 0
        # Fresh hardware reset: use only the two standard DCS commands,
        # allowing more than the usual 120 ms for factory defaults to load.
        print(json.dumps({'step': 'fresh-reset-without-vendor-unlock',
                          'status': status()}), flush=True)
        packet(0x05, 0x11)
        time.sleep(1.0)
        packet(0x05, 0x29)
        time.sleep(1.0)
        print(json.dumps({'step': 'factory-sleep-out-1000ms-display-on-1000ms',
                          'status': status(), 'display_status': read(0x09).hex()}), flush=True)
        time.sleep(3.0)
        print(json.dumps({'step': 'factory-wake-after-3-more-seconds',
                          'status': status(), 'display_status': read(0x09).hex()}), flush=True)
    elif action == 'standard':
        # The wrapper must retain independent, time-bounded cleanup.
        assert subprocess.run(['systemctl', 'is-active', '--quiet',
                               'tzx-display-test-timeout.timer']).returncode == 0
        unlock()
        result = {'panel_id': identity, 'steps': []}
        def capture(name):
            step = {'step': name, 'status': status()}
            result['steps'].append(step)
            print(json.dumps(step), flush=True)
        capture('before')
        # These standard controls do not alter analog or panel routing values.
        write1(0x51, 0xff)
        write1(0x53, 0x2c)
        write1(0x3a, 0x77)
        write1(0x11, 0)
        time.sleep(0.15)
        capture('sleep-out-with-dummy-parameter')
        write1(0x23, 0)
        write1(0x29, 0)
        time.sleep(0.15)
        capture('all-pixels-and-display-on-with-dummy-parameter')
        packet(0x05, 0x13)
        time.sleep(0.02)
        capture('normal-mode-no-parameter')
        packet(0x05, 0x23)
        packet(0x05, 0x29)
        time.sleep(0.15)
        capture('all-pixels-and-display-on-no-parameter')
        result['brightness'] = {f'{command:02x}': read(command).hex()
                                for command in (0x52, 0x54)}
        print(json.dumps(result, indent=2), flush=True)
    elif action == 'clock-wake':
        assert (parameters / 'hs_clock').read_text().strip() == 'Y'
        assert subprocess.run(['systemctl', 'is-active', '--quiet',
                               'tzx-display-test-timeout.timer']).returncode == 0
        # identity above includes DLY and has returned the clock to LP.
        # Restart HSC, then leave the clock lane out of every LP write.
        put(0x20, 0x1f)
        put(0x28, 0x20000010)
        put(0x48, 0xf02)
        put(0x10, (3 << 16) | 1)
        deadline = time.monotonic() + 0.04
        while get(0x10) & 1:
            if time.monotonic() > deadline:
                raise TimeoutError('pre-wake HS clock timeout')
            time.sleep(0.0001)
        put(0x20, 0xf)
        packet(0x05, 0x11)
        time.sleep(0.15)
        packet(0x05, 0x29)
        time.sleep(0.15)
        print(json.dumps({'step': 'sleep-out-and-on-with-continuous-clock',
                          'status': status()}), flush=True)
    elif action == 'ack':
        assert subprocess.run(['systemctl', 'is-active', '--quiet',
                               'tzx-display-test-timeout.timer']).returncode == 0
        unlock()
        for command in (0x21, 0x20, 0x29, 0x23, 0x13):
            packet(0x05, command, True)
            ctl = get(0x200)
            raw = bytes(host[0x240:0x250])
            print(json.dumps({'command': f'{command:02x}',
                              'bta_ctl': f'{ctl:08x}', 'raw_reply': raw.hex(),
                              'packet_received': bool(ctl & (1 << 25)),
                              'ack_error': int.from_bytes(raw[1:3], 'little')
                              if raw[0] & 63 == 2 and ctl & (1 << 25) else None}), flush=True)
            time.sleep(0.15)
            print(json.dumps({'command': f'{command:02x}', 'status': status()}), flush=True)
    elif action == 'long':
        assert subprocess.run(['systemctl', 'is-active', '--quiet',
                               'tzx-display-test-timeout.timer']).returncode == 0
        unlock()
        for name, payload in (
                ('long-inversion-on', bytes((0x21, 0))),
                ('long-inversion-off', bytes((0x20, 0))),
                ('long-brightness-check', bytes((0x51, 0x80))),
                ('long-brightness-restore', bytes((0x51, 0xff))),
                ('long-sleep-out', bytes((0x11, 0))),
                ('long-all-pixels-on', bytes((0x23, 0))),
                ('long-display-on', bytes((0x29, 0)))):
            long_write(payload)
            time.sleep(0.15)
            print(json.dumps({'step': name, 'status': status(),
                              'brightness': read(0x52).hex(),
                              'display_status': read(0x09).hex()}), flush=True)
        samples = []
        for _ in range(20):
            samples.append({'time': time.monotonic(), 'scanline': read(0x45).hex()})
            time.sleep(0.02)
        print(json.dumps({'step': 'scanline-without-video', 'samples': samples}), flush=True)
    elif video_status:
        print(json.dumps({'phase': 'after-previous-video', 'panel_id': identity,
                          'status': status()}), flush=True)
        print(json.dumps({'phase': 'standard-video-diagnostics',
                          'registers': {f'{command:02x}': read(command).hex()
                                        for command in (0x05, 0x06, 0x07, 0x08, 0x09, 0x45)}}), flush=True)
        unlock()
        write1(0x51, 0xff)
        write1(0x53, 0x2c)
        packet(0x05, 0x29)
        time.sleep(0.15)
        print(json.dumps({'phase': 'after-standard-display-on', 'status': status()}), flush=True)
    elif action == 'formats':
        assert subprocess.run(['systemctl', 'is-active', '--quiet',
                               'tzx-display-test-timeout.timer']).returncode == 0
        # Compare the generic short-write unlock used by Fuchsia's JD9365
        # driver. Retain the panel's factory voltage/GIP/gamma values.
        for command, value in ((0xe0, 0), (0xe1, 0x93), (0xe2, 0x65), (0xe3, 0xf8)):
            packet(0x23, command | (value << 8))
            time.sleep(0.005)
        print(json.dumps({'step': 'generic-unlock', 'status': status()}), flush=True)
        for name, kind, command in (
                ('dcs-inversion-on', 0x05, 0x21),
                ('dcs-inversion-off', 0x05, 0x20),
                ('dcs-all-pixels-on', 0x05, 0x23),
                ('dcs-normal', 0x05, 0x13),
                ('dcs-display-on', 0x05, 0x29),
                ('generic-one-byte-display-on', 0x13, 0x29),
                ('generic-two-byte-display-on', 0x23, 0x29),
                ('generic-two-byte-all-pixels', 0x23, 0x23)):
            packet(kind, command)
            time.sleep(0.05)
            print(json.dumps({'step': name, 'status': status()}), flush=True)
        write1(0x35, 0)
        time.sleep(0.02)
        print(json.dumps({'step': 'standard-tearing-control', 'status': status()}), flush=True)
        packet(0x05, 0x34)
        packet(0x05, 0x13)
        packet(0x05, 0x29)
    else:
        print(json.dumps({'panel_id': identity,
                          'status': status()}))
finally:
    write1(0xe0, 0)
    if video_status:
        put(0x20, 0x1f)
        put(0x28, 0x20000010)
        put(0x48, 0xf02)
        put(0x10, (3 << 16) | 1)
        deadline = time.monotonic() + 0.04
        while get(0x10) & 1:
            if time.monotonic() > deadline:
                put(0x10, 3 << 16)
                raise TimeoutError('HS clock restart timeout')
            time.sleep(0.0001)
        put(0x20, 0xf)
        put(0x14, saved_video_mode)
        put(0x4c, saved_video_cfg)
        put(0x48, saved_video_jump)
        put(0x10, 3 << 16)
        put(0x10, (3 << 16) | 1)
        time.sleep(0.1)
        print(json.dumps({'phase': 'video-restarted', 'line': get(0x2e0),
                          'inst': f'{get(0x2f0):08x}'}), flush=True)
    host.close()
    os.close(fd)
