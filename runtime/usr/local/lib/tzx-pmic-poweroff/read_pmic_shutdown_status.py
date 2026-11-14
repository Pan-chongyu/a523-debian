"""Read AXP717 power-on/off reasons and control; never acknowledge or write."""
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
    tx = C.create_string_buffer(bytes([reg]))
    rx = C.create_string_buffer(1)
    messages = (Msg*2)(Msg(addr, 0, 1, C.addressof(tx)), Msg(addr, 1, 1, C.addressof(rx)))
    result = libc.ioctl(fd, 0x707, C.byref(Transfer(messages, 2)))
    if result < 0:
        raise OSError(C.get_errno(), os.strerror(C.get_errno()))
    assert result == 2
    return rx.raw[0]


try:
    status = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'access': 'read-only', 'axp323_id': hex(read(0x36, 3)),
              'axp717': {hex(reg): hex(read(0x34, reg)) for reg in
                         (0, 1, 0x19, 0x1a, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x85)}}
    print(json.dumps(status, indent=2), flush=True)
finally:
    os.close(fd)
