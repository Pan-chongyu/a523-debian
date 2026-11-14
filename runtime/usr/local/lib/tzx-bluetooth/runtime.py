"""Guarded H4 attachment; radio readiness is verified before systemd READY."""
import hashlib
import ctypes
import os
from pathlib import Path
import signal
import select
import socket
import struct
import subprocess
import sys
import termios
import time

RELEASE = '7.3.3-tzx-a523-periph1'
CID = Path('/etc/tzx/device-cid').read_text().strip()


def guard():
    assert os.geteuid() == 0
    assert os.uname().release == RELEASE
    assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == CID


def hardware_start():
    module = Path('/lib/modules') / RELEASE / 'extra/tzx_bt_runtime.ko'
    expected = Path('/usr/local/lib/tzx-bluetooth/MODULE.sha256').read_text().split()[0]
    assert hashlib.sha256(module.read_bytes()).hexdigest() == expected
    subprocess.run(['modprobe', 'hci_uart'], check=True)
    subprocess.run(['modprobe', 'tzx_bt_runtime'], check=True)
    assert Path('/sys/class/tty/ttyS1/device').resolve().is_relative_to(
        Path('/sys/devices/platform/tzx-bt-uart'))
    print('TZX_BT_RESET_RELEASED_BEFORE_SHARED_FIRMWARE', flush=True)


def notify_ready():
    address = os.environ.get('NOTIFY_SOCKET')
    if not address:
        return
    if address.startswith('@'):
        address = '\0' + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.connect(address)
        client.sendall(b'READY=1\nSTATUS=AIC8800D80 H4 radio powered')


def management(opcode, index, payload=b''):
    """Linux Bluetooth MGMT protocol, independent of CLI stdin/event loops."""
    with socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI) as client:
        # Debian's Python HCI address parser supports only the legacy device
        # tuple. Bind the Linux sockaddr_hci including its control channel.
        address = ctypes.create_string_buffer(struct.pack('=HHH', socket.AF_BLUETOOTH, 65535, 3))
        libc = ctypes.CDLL(None, use_errno=True)
        libc.bind.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
        libc.bind.restype = ctypes.c_int
        if libc.bind(client.fileno(), address, 6) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        client.settimeout(2)
        packet = struct.pack('<HHH', opcode, index, len(payload)) + payload
        # MGMT commands are packets. In particular an early Invalid Index
        # response can make this kernel return zero from sendmsg; sendall
        # would then repeatedly enqueue the same command.
        written = client.send(packet)
        if written not in (0, len(packet)):
            raise OSError('short Bluetooth MGMT packet')
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            packet = client.recv(4096)
            event, device, length = struct.unpack_from('<HHH', packet)
            if device != index or len(packet) != length + 6 or length < 3:
                continue
            command, status = struct.unpack_from('<HB', packet, 6)
            if event in (1, 2) and command == opcode:
                return status, packet[9:]
        raise TimeoutError('Bluetooth MGMT command timed out')


def prepare_uart():
    """Prime the controller with the standard sequence verified on this board.

    An initial Linux-only attach stalls at Write Extended Inquiry Response.
    The same command succeeds on the raw UART and subsequent H4 setup works.
    This is a volatile initialization workaround, not an OTP operation.
    """
    assert not list(Path('/sys/class/bluetooth').glob('hci*'))
    fd = os.open('/dev/ttyS1', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = termios.tcgetattr(fd)
    try:
        cfg = termios.tcgetattr(fd)
        cfg[0] = cfg[1] = cfg[3] = 0
        cfg[2] = termios.CS8 | termios.CLOCAL | termios.CREAD | termios.CRTSCTS
        cfg[4] = cfg[5] = termios.B1500000
        cfg[6][termios.VMIN] = cfg[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, cfg)
        termios.tcflush(fd, termios.TCIOFLUSH)
        address = bytes([2]) + hashlib.sha256((CID + ':bluetooth').encode()).digest()[:5]
        # AIC's supplied libbt aic_hardware.c documents 0xfc70 and its reversed
        # six-byte parameter. This sets volatile controller RAM, not OTP.
        for opcode, payload in ((0x0c03, b''), (0x1001, b''), (0x0c52, bytes(241)),
                                (0x0c03, b''), (0x0c52, bytes(241)),
                                (0xfc70, address[::-1]), (0x1009, b'')):
            packet = b'\x01' + struct.pack('<HB', opcode, len(payload)) + payload
            assert os.write(fd, packet) == len(packet)
            data = bytearray()
            end = time.monotonic() + 2
            while time.monotonic() < end:
                ready, _, _ = select.select([fd], [], [], max(0, end-time.monotonic()))
                if not ready:
                    break
                data.extend(os.read(fd, 1024))
            assert (len(data) >= 7 and data[:2] == b'\x04\x0e' and
                    struct.unpack_from('<H', data, 4)[0] == opcode and data[6] == 0), (
                        'HCI initialization failed', hex(opcode), data.hex())
            if opcode == 0x1009:
                assert data[7:13] == address[::-1], 'Bluetooth address readback mismatch'
                print('TZX_BT_STABLE_ADDRESS', address.hex(':'), flush=True)
        print('TZX_BT_UART_STANDARD_INIT_VERIFIED', flush=True)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        os.close(fd)


def attach():
    prepare_uart()
    child = subprocess.Popen(['btattach', '-B', '/dev/ttyS1', '-S', '1500000', '-P', 'h4'])
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child.poll() is None:
            child.send_signal(signal.SIGINT)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        deadline = time.monotonic() + 28
        last_status = None
        while time.monotonic() < deadline and not stopping:
            if child.poll() is not None:
                raise RuntimeError('btattach exited before controller initialization')
            controllers = [p for p in Path('/sys/class/bluetooth').glob('hci*')
                           if p.resolve().is_relative_to(Path('/sys/devices/platform/tzx-bt-uart'))]
            if len(controllers) == 1:
                controller = controllers[0].name
                index = int(controller.removeprefix('hci'))
                for radio in Path('/sys/class/rfkill').glob('rfkill*'):
                    if (radio / 'type').read_text().strip() == 'bluetooth' and (
                            radio / 'name').read_text().strip() == controller:
                        (radio / 'soft').write_text('0\n')
                # HCI sysfs appears before controller setup and MGMT Index Added.
                try:
                    status, info = management(4, index)  # Read Controller Information
                    current = ('MGMT_INFO', status, len(info))
                    if current != last_status:
                        print(*current, flush=True)
                        last_status = current
                    if status or len(info) < 17:
                        time.sleep(0.5)
                        continue
                    powered = bool(struct.unpack_from('<I', info, 13)[0] & 1)
                    if not powered:
                        management(5, index, b'\x01')  # Set Powered
                        time.sleep(0.5)
                        continue
                    print('TZX_BT_HCI_POWERED', controller, flush=True)
                    notify_ready()
                    return child.wait()
                except (TimeoutError, OSError) as error:
                    current = ('MGMT_WAIT', type(error).__name__, str(error))
                    if current != last_status:
                        print(*current, flush=True)
                        last_status = current
            time.sleep(0.5)
        if not stopping:
            raise RuntimeError('Bluetooth controller did not become ready')
        return 0
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    guard()
    if sys.argv[1:] == ['hardware-start']:
        hardware_start()
    elif sys.argv[1:] == ['attach']:
        sys.exit(attach())
    else:
        raise SystemExit('usage: runtime.py hardware-start|attach')
