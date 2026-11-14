"""Run commands on this tablet's initramfs USB debug console."""
import argparse
import sys
import time
from fel_device import ROOT
import serial
from serial.tools import list_ports

parser = argparse.ArgumentParser()
parser.add_argument("--command", required=True)
parser.add_argument("--seconds", type=float, default=3)
parser.add_argument("--output")
parser.add_argument("--interrupt", action="store_true")
args = parser.parse_args()
ports = [p for p in list_ports.comports() if p.vid == 0x1D6B and p.pid == 0x0104]
if len(ports) != 1:
    raise RuntimeError(f"Expected one TZX USB debug console, found {len(ports)}")
data = bytearray()
with serial.Serial(ports[0].device, 115200, timeout=0.2, write_timeout=3) as link:
    link.dtr = True
    if args.interrupt:
        link.write(b"\x03")
    link.write(b"\r\n")
    time.sleep(0.2)
    link.read(link.in_waiting)
    link.write(args.command.encode() + b"\n")
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        try:
            data.extend(link.read(65536))
        except serial.SerialException:
            break
text = data.decode("utf-8", errors="replace")
if args.output:
    (ROOT / "evidence" / args.output).write_text(text, encoding="utf-8")
sys.stdout.buffer.write(text.encode("utf-8"))
