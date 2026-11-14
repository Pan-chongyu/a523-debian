"""Copy a local executable to the temporary USB shell and verify its SHA256."""
import argparse
import gzip
import hashlib
import re
import time
from pathlib import Path
from fel_device import ROOT
import serial
from serial.tools import list_ports

parser = argparse.ArgumentParser()
parser.add_argument("--file", type=Path, required=True)
parser.add_argument("--remote", required=True)
parser.add_argument("--raw", action="store_true", help="Transfer an already compressed file unchanged")
parser.add_argument("--chunk-size", type=int, default=2048)
parser.add_argument("--pause", type=float, default=0.01)
args = parser.parse_args()
assert re.fullmatch(r"/tmp/[a-zA-Z0-9_.-]+", args.remote)
assert 512 <= args.chunk_size <= 65536 and args.pause >= 0
raw = args.file.read_bytes()
compressed = raw if args.raw else gzip.compress(raw, compresslevel=6, mtime=0)
expected = hashlib.sha256(raw).hexdigest()
ports = [p for p in list_ports.comports() if p.vid == 0x1D6B and p.pid == 0x0104]
assert len(ports) == 1
output = bytearray()
with serial.Serial(ports[0].device, 115200, timeout=0.2, write_timeout=15) as link:
    link.dtr = True
    link.write(b"\x03\r\n")
    time.sleep(0.3)
    link.read(link.in_waiting)
    receiver = args.remote if args.raw else args.remote + ".gz"
    unpack = "" if args.raw else f"gzip -df {receiver}; "
    command = (f"stty raw -echo; echo TZX_TRANSFER_READY; head -c {len(compressed)} > {receiver}; "
               f"stty sane; {unpack}chmod 755 {args.remote}; "
               f"sha256sum {args.remote}; echo TZX_TRANSFER_DONE\n")
    link.write(command.encode())
    ready = bytearray()
    until_ready = time.monotonic() + 10
    while time.monotonic() < until_ready:
        ready.extend(link.read(65536))
        if b'TZX_TRANSFER_READY\n' in ready or b'TZX_TRANSFER_READY\r\n' in ready:
            break
    else:
        raise RuntimeError("Raw USB receiver did not become ready: " + repr(ready[-500:]))
    last = time.monotonic()
    started = last
    for offset in range(0, len(compressed), args.chunk_size):
        link.write(compressed[offset:offset + args.chunk_size])
        if args.pause:
            time.sleep(args.pause)
        if time.monotonic() - last >= 10:
            print(f"USB transfer: {offset}/{len(compressed)} bytes, {(offset/(time.monotonic()-started)/1048576):.2f} MiB/s", flush=True)
            last = time.monotonic()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        output.extend(link.read(65536))
        if b"TZX_TRANSFER_DONE" in output:
            break
text = output.decode("utf-8", errors="replace")
(ROOT / "evidence/usb-transfer.txt").write_text(text, encoding="utf-8")
assert expected in text, "USB transfer digest mismatch: " + text[-2000:]
print(f"USB transfer verified: {args.remote}, {len(raw)} bytes, SHA256 {expected}")
