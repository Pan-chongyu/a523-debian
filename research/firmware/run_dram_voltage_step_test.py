"""Bounded manual comparison after observing the init library's 1260mV request.

DCDC3 wiring is inferred from AXP717's DRAM designation and the related
A523/AXP717/323 board, not physically measured. No PMIC enables change.
The earlier retired diagnostic remains disabled. This version applies and
reads back the setpoint BEFORE drop_caches or allocating the high-page pool.
"""
import argparse
import ctypes as C
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('phase', choices=('preflight', 'run', 'restore'))
parser.add_argument('--millivolts', type=int, choices=(1200, 1260), default=1200)
args = parser.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/bus/i2c/devices/0-0034').exists()
assert not Path('/sys/bus/i2c/devices/0-0036').exists()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
folder = Path('/var/lib/tzx/diagnostics/dram-voltage-step')
folder.mkdir(parents=True, exist_ok=True)
lock = (folder/'lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
state_path = folder/'active.json'


class Msg(C.Structure):
    _fields_ = [('addr', C.c_uint16), ('flags', C.c_uint16),
                ('length', C.c_uint16), ('buf', C.c_void_p)]


class Transfer(C.Structure):
    _fields_ = [('msgs', C.POINTER(Msg)), ('count', C.c_uint32)]


libc = C.CDLL(None, use_errno=True)
i2c = os.open('/dev/i2c-0', os.O_RDWR)


def transaction(messages):
    transfer = Transfer(messages, len(messages))
    result = libc.ioctl(i2c, 0x707, C.byref(transfer))
    if result < 0:
        raise OSError(C.get_errno(), os.strerror(C.get_errno()))
    assert result == len(messages), result


def read(addr, reg):
    tx, rx = C.create_string_buffer(bytes([reg])), C.create_string_buffer(1)
    transaction((Msg*2)(Msg(addr, 0, 1, C.addressof(tx)),
                       Msg(addr, 1, 1, C.addressof(rx))))
    return rx.raw[0]


def millivolts(value):
    selector = value & 0x7f
    return 500+10*selector if selector <= 70 else 1200+20*(selector-70)


def snapshot():
    return {'axp717': {hex(reg): hex(read(0x34, reg))
                       for reg in (0x80, 0x83, 0x84, 0x85, 0x86, 0x98)},
            'axp323': {hex(reg): hex(read(0x36, reg)) for reg in (0x03, 0x10, 0x13, 0x14, 0x15)}}


def store(state):
    temporary = state_path.with_suffix('.tmp')
    with temporary.open('w') as output:
        json.dump(state, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(state_path)
    fd = os.open(folder, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ramp(destination):
    assert destination in (0xbc, 0xc6, 0xc9)
    current = read(0x34, 0x85)
    assert 0xbc <= current <= 0xc9 and current & 0x80
    direction = 1 if destination > current else -1
    for value in range(current+direction, destination+direction, direction):
        assert 0xbc <= value <= 0xc9 and value & 0x80
        tx = C.create_string_buffer(bytes([0x85, value]))
        transaction((Msg*1)(Msg(0x34, 0, 2, C.addressof(tx))))
        time.sleep(0.01)
        assert read(0x34, 0x85) == value
        print('DRAM_STEP_READBACK', hex(value), millivolts(value), flush=True)
    assert read(0x34, 0x85) == destination


def restore():
    if not state_path.exists():
        print('DRAM_STEP_NO_STATE_NO_WRITE', boot, flush=True)
        return
    saved = json.loads(state_path.read_text())
    assert saved['original_register'] == 0xbc
    assert saved['target_register'] in (0xc6, 0xc9)
    assert saved['cid'] == '3e01ff55454d20202010209170281b59'
    assert read(0x36, 0x03) == 0x49 and read(0x34, 0x80) == 0x0f
    ramp(0xbc)
    saved['restored_in_boot'] = boot
    saved['restore_register_readback'] = hex(read(0x34, 0x85))
    store(saved)
    print('DRAM_STEP_RESTORED', json.dumps(saved), flush=True)


if args.phase == 'restore':
    restore()
    raise SystemExit(0)

assert struct.unpack('>4I', Path('/sys/firmware/devicetree/base/memory@40000000/reg').read_bytes()) == (0, 0x40000000, 1, 0)
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
for name in ('panfrost', 'tzx_cpufreq_divider', 'tzx_cpu_stream_probe', 'tzx_sram_log'):
    assert not Path('/sys/module', name).exists(), name
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert read(0x36, 0x03) == 0x49 and read(0x34, 0x80) == 0x0f
assert [read(0x34, reg) for reg in (0x83, 0x84, 0x85, 0x86, 0x98)] == [0xa8, 0xa8, 0xbc, 0x00, 0x0d]
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x2e000) as view:
        raw = b''.join(struct.pack('<I', struct.unpack_from('<I', view, offset)[0])
                       for offset in range(0, 4096, 4))
finally:
    os.close(fd)
assert struct.unpack_from('<I', raw)[0] == 0x4452414d
boot_log = raw[0x100:0x100+3500].split(b'\0', 1)[0].decode('ascii')
assert 'DRAM_VCC set to 1260 mv' in boot_log
binary = Path('/home/debian/library-copy-coherency-v8')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
assert all(int(path.read_text()) < 65000 for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'))
target = 0xc6 if args.millivolts == 1200 else 0xc9
prefix = '/home/debian/copy-dram-step-'+str(args.millivolts)+'-v8'
assert not list(Path('/home/debian').glob(Path(prefix).name+'-*'))
before = snapshot()
print('DRAM_STEP_PREFLIGHT', json.dumps({'boot_id': boot, 'before': before,
      'boot_log': boot_log, 'target_mV': args.millivolts, 'voltage_written': False}), flush=True)
if args.phase == 'preflight':
    raise SystemExit(0)
state = {'boot_id': boot, 'original_register': 0xbc, 'target_register': target,
         'cid': '3e01ff55454d20202010209170281b59',
         'board_mapping': 'reference_inference_not_measured', 'before': before,
         'boot_log': boot_log, 'full_4GiB': True}
store(state)
try:
    # Apply and print before the cache-drop/high-pool path that previously reset.
    ramp(target)
    state['applied_register_readback'] = hex(read(0x34, 0x85))
    store(state)
    print('DRAM_STEP_APPLIED_BEFORE_WORKLOAD', json.dumps(state), flush=True)
    os.sync()
    Path('/proc/sys/vm/drop_caches').write_text('1\n')
    env = {key: value for key, value in os.environ.items()
           if key not in ('TZX_COPY_HIGH_TARGETS', 'TZX_COPY_LOW_TARGETS')}
    env['TZX_COPY_HIGH_TARGETS'] = '1'
    result = subprocess.run([str(binary), '300', prefix, '255', 'libc'], env=env, timeout=350)
    assert read(0x34, 0x85) == target
    state['copy_returncode'] = result.returncode
    state['after_workload'] = snapshot()
    store(state)
    print('DRAM_STEP_COPY_RESULT', json.dumps(state), flush=True)
finally:
    restore()
raise SystemExit(result.returncode)
