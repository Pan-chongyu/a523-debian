"""Keep the first-stage USB shell connected while its corrected init is installed."""
import time
from fel_device import ROOT
import serial
from serial.tools import list_ports

deadline=time.monotonic()+45
while time.monotonic()<deadline:
    ports=[p for p in list_ports.comports() if p.vid==0x1d6b and p.pid==0x0104]
    if ports:
        try:
            link=serial.Serial(ports[0].device,115200,timeout=.3,write_timeout=3)
            break
        except serial.SerialException: pass
    time.sleep(1)
else: raise RuntimeError("USB console did not become ready")
try:
    link.dtr=True
    link.write(b"\r\ntrap '' HUP; stty clocal -hupcl; echo HOLD_READY; cat /proc/uptime; cat /proc/1/comm\n")
    time.sleep(.5)
    first=link.read(65536).decode(errors="replace")
    print(first,flush=True)
    assert "HOLD_READY" in first
    until=time.monotonic()+1200
    while time.monotonic()<until:
        data=link.read(65536)
        if data: print(data.decode(errors="replace"),flush=True)
        flag=ROOT/"build/console-command.txt"
        if flag.exists():
            cmd=flag.read_bytes();flag.unlink();link.write(cmd+b"\n")
        if (ROOT/"build/release-console").exists(): break
finally: link.close()
