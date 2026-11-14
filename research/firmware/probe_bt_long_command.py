"""Compare ordinary and paced UART writes using standard volatile HCI commands."""
from pathlib import Path
import fcntl
import os
import select
import struct
import termios
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not list(Path('/sys/class/bluetooth').glob('hci*'))
fd = os.open('/dev/ttyS1', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
old = termios.tcgetattr(fd)


def counters():
    data = bytearray(80)
    fcntl.ioctl(fd, 0x545D, data, True)  # TIOCGICOUNT
    values = struct.unpack('20i', data)
    return dict(zip(('cts', 'dsr', 'rng', 'dcd', 'rx', 'tx', 'frame', 'overrun', 'parity', 'brk', 'buf_overrun'), values))


def command(opcode, payload=b'', pace=False):
    before = counters()
    packet = b'\x01' + struct.pack('<HB', opcode, len(payload)) + payload
    if pace:
        for offset in range(0, len(packet), 16):
            assert os.write(fd, packet[offset:offset+16]) == len(packet[offset:offset+16])
            time.sleep(.003)
    else:
        assert os.write(fd, packet) == len(packet)
    data = bytearray()
    end = time.monotonic() + 2
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], max(0, end-time.monotonic()))
        if not ready:
            break
        data.extend(os.read(fd, 1024))
    print('HCI_TEST', hex(opcode), 'paced', pace, 'reply', data.hex(), 'before', before, 'after', counters(), flush=True)


try:
    cfg = termios.tcgetattr(fd)
    cfg[0] = cfg[1] = cfg[3] = 0
    cfg[2] = termios.CS8 | termios.CLOCAL | termios.CREAD | termios.CRTSCTS
    cfg[4] = cfg[5] = termios.B1500000
    cfg[6][termios.VMIN] = cfg[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, cfg)
    termios.tcflush(fd, termios.TCIOFLUSH)
    command(0x0c03)
    command(0x1001)
    command(0x0c52, bytes(241))
    command(0x0c03)
    command(0x0c52, bytes(241), pace=True)
finally:
    termios.tcsetattr(fd, termios.TCSANOW, old)
    os.close(fd)
