"""Send standard read-only HCI identification commands over candidate UART1."""
from pathlib import Path
import os
import select
import termios
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/module/tzx_bt_runtime').is_dir()
fd = os.open('/dev/ttyS1', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
old = termios.tcgetattr(fd)
try:
    for baud, flow in [(1500000, True), (1500000, False), (115200, False)]:
        cfg = termios.tcgetattr(fd)
        cfg[0] = cfg[1] = cfg[3] = 0
        cfg[2] = termios.CS8 | termios.CLOCAL | termios.CREAD | (termios.CRTSCTS if flow else 0)
        cfg[4] = cfg[5] = getattr(termios, 'B'+str(baud))
        cfg[6][termios.VMIN] = cfg[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, cfg)
        termios.tcflush(fd, termios.TCIOFLUSH)
        # HCI Read Local Version Information, opcode 0x1001.
        os.write(fd, bytes.fromhex('01011000'))
        data = bytearray(); end = time.monotonic()+2
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], max(0, end-time.monotonic()))
            if not ready: break
            part = os.read(fd, 256)
            if part: data.extend(part)
        print('UART_RESULT', baud, 'flow', flow, 'bytes', data.hex(), flush=True)
        if data[:3] == bytes.fromhex('040e0c') and bytes.fromhex('011000') in data:
            print('HCI_LOCAL_VERSION_RESPONSE_VERIFIED', flush=True)
            break
finally:
    termios.tcsetattr(fd, termios.TCSANOW, old)
    os.close(fd)
