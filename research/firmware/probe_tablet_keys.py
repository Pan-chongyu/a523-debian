"""Observe GPIO inputs and AXP717 PEK event bits for a bounded key test."""
import ctypes as c
import fcntl
import json
import mmap
import os
from pathlib import Path
import struct
import time

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/bus/i2c/devices/0-0034/driver').exists()
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
pio = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x02000000)
rpio = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x07022000)
os.close(fd)


class SMBusData(c.Union):
    _fields_ = [('byte', c.c_uint8), ('word', c.c_uint16), ('block', c.c_uint8*34)]


class SMBusIoctl(c.Structure):
    _fields_ = [('read_write', c.c_uint8), ('command', c.c_uint8),
               ('size', c.c_uint32), ('data', c.POINTER(SMBusData))]


bus = os.open('/dev/i2c-0', os.O_RDWR | os.O_CLOEXEC)
fcntl.ioctl(bus, 0x0706, 0x34)


def reg(address, value=None):
    data = SMBusData()
    if value is not None:
        data.byte = value
    request = SMBusIoctl(1 if value is None else 0, address, 2, c.pointer(data))
    fcntl.ioctl(bus, 0x0720, request)
    return data.byte


def snapshot():
    values = {}
    for name, base, index in [(chr(65+i), pio, i) for i in range(1, 11)]+[('L', rpio, 0), ('M', rpio, 1)]:
        offset = index*0x30
        mask = 0
        for pin in range(32):
            mux = (struct.unpack_from('<I', base, offset+(pin//8)*4)[0] >> ((pin%8)*4)) & 15
            if mux == 0:
                mask |= 1 << pin
        values[name] = struct.unpack_from('<I', base, offset+0x10)[0] & mask
    return values


started = time.monotonic()
previous = snapshot()
print(json.dumps({'event': 'BASELINE', 'gpio_input_values': previous,
                  'pmic_irq_enable1': reg(0x42), 'pmic_irq_status1': reg(0x49)}), flush=True)
# Mainline AXP717 mapping: IRQ1 status is 0x49, PEK falling/rising bits 1/0.
# Clear only stale PEK edge flags, never USB, battery or charger flags.
pending = reg(0x49) & 3
if pending:
    reg(0x49, pending)
try:
    while time.monotonic()-started < 180:
        current = snapshot()
        changes = {bank: {'before': previous[bank], 'after': value, 'xor': value ^ previous[bank]}
                   for bank, value in current.items() if value != previous[bank]}
        pending = reg(0x49) & 3
        if changes or pending:
            print(json.dumps({'second': round(time.monotonic()-started, 3),
                'gpio_changes': changes, 'pek_edges': pending}), flush=True)
        if pending:
            reg(0x49, pending)
        previous = current
        time.sleep(0.02)
finally:
    os.close(bus)
    pio.close()
    rpio.close()
print('KEY_OBSERVATION_FINISHED', flush=True)
