"""Bounded ID-only reads on two documented TWI candidate pin pairs."""
import ctypes as C
import errno
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
module = Path('/home/debian/tzx_candidate_i2c.ko')
assert hashlib.sha256(module.read_bytes()).hexdigest() == 'f8a610c2873a9fc391921838341c3436f9fd96aeec8d3ac26968f8c22b98a1cb'
assert not Path('/sys/module/tzx_candidate_i2c').exists()
assert subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip() == ''
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096


class Msg(C.Structure):
    _fields_ = [('addr', C.c_uint16), ('flags', C.c_uint16), ('length', C.c_uint16), ('buf', C.c_void_p)]


class Transfer(C.Structure):
    _fields_ = [('msgs', C.POINTER(Msg)), ('count', C.c_uint32)]


libc = C.CDLL(None, use_errno=True)


def read_byte(fd, addr, reg):
    # One address-pointer byte, then a read. Never write a configuration
    # value or send a two-byte pointer to an unidentified 8-bit peripheral.
    tx = C.create_string_buffer(bytes([reg]))
    rx = C.create_string_buffer(1)
    messages = (Msg*2)(Msg(addr, 0, 1, C.addressof(tx)), Msg(addr, 1, 1, C.addressof(rx)))
    result = libc.ioctl(fd, 0x707, C.byref(Transfer(messages, 2)))
    if result < 0:
        return {'errno': C.get_errno(), 'message': os.strerror(C.get_errno())}
    assert result == 2
    return hex(rx.raw[0])


def pins(candidate):
    base, first = (0x150, 2) if candidate == 1 else (0xc0, 3)
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x02000000) as view:
            return {'mux': hex(struct.unpack_from('<I', view, base)[0] & (0xff << (first*4))),
                    'data': hex(struct.unpack_from('<I', view, base+0x10)[0] & (3 << first)),
                    'pull': hex(struct.unpack_from('<I', view, base+0x24)[0] & (0xf << (first*2)))}
    finally:
        os.close(fd)


def run(*command):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=20).stdout


report = {'boot_id': BOOT, 'identification_only': True, 'PMIC_clock_reset_writes': False,
          'limitations': 'No ACK may mean unpowered/reset/no MCLK or different wiring; it does not prove hardware absence.',
          'candidates': []}
run('systemd-run', '--unit=tzx-candidate-i2c-independent-unload', '--on-active=80s',
    '/sbin/rmmod', 'tzx_candidate_i2c')
try:
    for candidate in (1, 3):
        before = pins(candidate)
        first = 2 if candidate == 1 else 3
        assert all((int(before['mux'], 16) >> (pin*4)) & 15 in (0, 15)
                   for pin in (first, first+1)), before
        run('insmod', str(module), 'candidate='+str(candidate))
        entry = {'candidate_TWI': candidate, 'Linux_bus': 16+candidate,
                 'pins_before': before, 'reads': {}}
        fd = os.open('/dev/i2c-'+str(16+candidate), os.O_RDWR)
        try:
            addresses = (0x0c, 0x0d, 0x0e, 0x12, 0x13, 0x18, 0x19, 0x1c, 0x1d,
                         0x26, 0x28, 0x38, 0x48, 0x4c, 0x68, 0x69, 0x6a, 0x6b) if candidate == 1 else (
                         0x10, 0x1a, 0x21, 0x2c, 0x30, 0x36, 0x37, 0x3c)
            for address in addresses:
                registers = (0x0f, 0x00, 0x01) if candidate == 1 else (0xf0, 0xf1, 0x0a, 0x0b)
                values = {hex(reg): read_byte(fd, address, reg) for reg in registers}
                entry['reads'][hex(address)] = values
        finally:
            os.close(fd)
        run('rmmod', 'tzx_candidate_i2c')
        after = pins(candidate)
        assert before == after, (before, after)
        entry['pins_after'] = after
        entry['responding_addresses'] = [addr for addr, values in entry['reads'].items()
                                         if any(isinstance(value, str) for value in values.values())]
        report['candidates'].append(entry)
        print('CANDIDATE_TWI_ID_READS_AND_PIN_RESTORE', json.dumps(entry), flush=True)
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    assert subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip() == ''
    for name in ('tzx-display', 'tzx-touch', 'tzx-wifi', 'tzx-bluetooth', 'tzx-audio', 'tzx-cpu-cooling', 'lightdm'):
        assert subprocess.check_output(['systemctl', 'is-active', name+'.service'], text=True).strip() == 'active'
    target = Path('/home/debian/candidate-sensor-id-reads.json')
    with target.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print('CANDIDATE_SENSOR_ID_PROBE_RESTORED', json.dumps({
          'boot_id': BOOT, 'responding': {entry['candidate_TWI']: entry['responding_addresses'] for entry in report['candidates']}}), flush=True)
finally:
    if Path('/sys/module/tzx_candidate_i2c').exists():
        run('rmmod', 'tzx_candidate_i2c')
    run('systemctl', 'stop', 'tzx-candidate-i2c-independent-unload.timer')
