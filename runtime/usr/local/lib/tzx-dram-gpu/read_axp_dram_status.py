"""Read only the identified PMIC voltage/enable registers with I2C_RDWR."""
import ctypes as C
import json
import os
from pathlib import Path

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()


class Msg(C.Structure):
    _fields_ = [('addr', C.c_uint16), ('flags', C.c_uint16),
                ('length', C.c_uint16), ('buf', C.c_void_p)]


class Transfer(C.Structure):
    _fields_ = [('msgs', C.POINTER(Msg)), ('count', C.c_uint32)]


libc = C.CDLL(None, use_errno=True)
fd = os.open('/dev/i2c-0', os.O_RDWR)


def read(addr, reg):
    tx, rx = C.create_string_buffer(bytes([reg])), C.create_string_buffer(1)
    messages = (Msg*2)(Msg(addr, 0, 1, C.addressof(tx)), Msg(addr, 1, 1, C.addressof(rx)))
    result = libc.ioctl(fd, 0x707, C.byref(Transfer(messages, 2)))
    if result < 0:
        raise OSError(C.get_errno(), os.strerror(C.get_errno()))
    assert result == 2
    return rx.raw[0]


try:
    status = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'access': 'read-only',
              'axp717': {hex(r): hex(read(0x34, r)) for r in (0x03, 0x80, 0x83, 0x84, 0x85, 0x86, 0x98)},
              'axp323': {hex(r): hex(read(0x36, r)) for r in (0x03, 0x10, 0x13, 0x14, 0x15)}}
    selector = int(status['axp717']['0x85'], 16) & 0x7f
    status['dcdc3_setpoint_mV'] = 500+selector*10 if selector <= 70 else 1200+(selector-70)*20
    print(json.dumps(status, indent=2), flush=True)
finally:
    os.close(fd)
