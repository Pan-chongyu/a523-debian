"""Capture the tablet's USB kernel console directly, without sending commands."""
import argparse
from pathlib import Path
import time
from fel_device import ROOT
import serial
from serial.tools import list_ports

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=360)
parser.add_argument('--output', required=True)
parser.add_argument('--wait-seconds', type=int, default=0)
parser.add_argument('--reconnect', action='store_true')
parser.add_argument('--timestamps', action='store_true')
args = parser.parse_args()
assert 1 <= args.seconds <= 900 and Path(args.output).name == args.output
assert 0 <= args.wait_seconds <= 120
deadline = time.monotonic() + args.wait_seconds
while True:
    ports = [port for port in list_ports.comports()
             if port.vid == 0x1d6b and port.pid == 0x0104
             and port.serial_number == 'TZX-A523-20261109']
    assert len(ports) <= 1
    if ports:
        try:
            link = serial.Serial(ports[0].device, 115200, timeout=0.25, write_timeout=3)
            break
        except serial.SerialException:
            if time.monotonic() >= deadline:
                raise
    assert time.monotonic() < deadline, 'Expected tablet USB console did not appear'
    time.sleep(0.5)
count = 0
capture_start = time.monotonic()
with (ROOT / 'evidence' / args.output).open('w', encoding='utf-8', buffering=1) as output:
    output.write('HOST_USB_KERNEL_CONSOLE_CAPTURE_STARTED\n')
    print('HOST_USB_KERNEL_CONSOLE_CAPTURE_STARTED', ports[0].device, flush=True)
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline:
            if link is None:
                ports = [port for port in list_ports.comports()
                         if port.vid == 0x1d6b and port.pid == 0x0104
                         and port.serial_number == 'TZX-A523-20261109']
                assert len(ports) <= 1
                if ports:
                    try:
                        link = serial.Serial(ports[0].device, 115200, timeout=0.25, write_timeout=3)
                        link.dtr = True
                        output.write('\nHOST_USB_CONSOLE_RECONNECTED\n')
                        if args.timestamps:
                            output.write('HOST_CAPTURE_ELAPSED_S %.3f USB_RECONNECTED\n' % (time.monotonic()-capture_start))
                    except serial.SerialException:
                        link = None
                if link is None:
                    time.sleep(0.5)
                    continue
            try:
                data = link.read(65536)
            except serial.SerialException as error:
                output.write('\nHOST_USB_DISCONNECTED ' + str(error) + '\n')
                if args.timestamps:
                    output.write('HOST_CAPTURE_ELAPSED_S %.3f USB_DISCONNECTED\n' % (time.monotonic()-capture_start))
                link.close()
                link = None
                if args.reconnect:
                    continue
                break
            if data:
                output.write(data.decode('utf-8', errors='replace'))
                output.flush()
                count += len(data)
    finally:
        if link is not None:
            link.close()
    output.write('\nHOST_USB_KERNEL_CONSOLE_CAPTURE_END bytes=' + str(count) + '\n')
print('HOST_USB_KERNEL_CONSOLE_CAPTURE_END', count, flush=True)
