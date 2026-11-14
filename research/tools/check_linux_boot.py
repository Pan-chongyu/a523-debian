"""Observe the Linux USB console, or capture the watchdog's FEL result."""
import json
import struct
import time
from fel_device import Device, ROOT, libusb_package
import serial
from serial.tools import list_ports

report = {"linux_usb_console": False}
deadline = time.monotonic() + 150
while time.monotonic() < deadline:
    ports = [p for p in list_ports.comports() if p.vid == 0x1D6B and p.pid == 0x0104]
    if ports:
        port = ports[0].device
        report["port"] = port
        with serial.Serial(port, 115200, timeout=0.25, write_timeout=3) as link:
            link.dtr = True
            link.write(b"\r\n")
            time.sleep(1)
            link.write(b"uname -a\ncat /sys/class/block/mmcblk0/device/cid\ncat /proc/partitions\ncat /proc/meminfo | head -n 4\ndmesg | tail -n 100\n")
            output = bytearray()
            until = time.monotonic() + 7
            while time.monotonic() < until:
                output.extend(link.read(65536))
        text = output.decode("utf-8", errors="replace")
        (ROOT / "evidence/linux-usb-console.txt").write_text(text, encoding="utf-8")
        report.update(linux_usb_console=True, output=text)
        break
    time.sleep(1)
else:
    report["usb_devices"] = [{"vid": hex(d.idVendor), "pid": hex(d.idProduct)}
                             for d in libusb_package.find(find_all=True)]
    if libusb_package.find(idVendor=0x1F3A, idProduct=0xEFE8) is not None:
        dev = Device(timeout=2000)
        try:
            dev.connect()
            report["fel_rtc"] = [f"0x{x:08x}" for x in struct.unpack("<8I", dev._read_raw(0x07090100, 32))]
            report["sram_receipt"] = dev._read_raw(0x2E000, 64).hex()
            report["sram_log"] = dev._read_raw(0x2E100, 3504).split(b"\0")[0].decode("ascii", errors="replace")
        except Exception as error:
            report["fel_error"] = repr(error)
        finally:
            dev.close()
(ROOT / "evidence/linux-boot-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2), flush=True)
