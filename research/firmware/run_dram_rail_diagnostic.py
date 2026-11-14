"""Bounded, reversible AXP717 DCDC3 nominal-voltage comparison, never auto-started.

The manufacturer's AXP717 power table names DCDC3 VCC-DRAM; the A523
LPDDR3 specification is 1.14..1.30 V, nominal 1.20 V. Board wiring remains
inferred from those references and the closely related A523/AXP717/323 board,
not measured. Only register 0x85 changes; bit 7 (DVM) is preserved.
"""
import argparse
import ctypes as C
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('phase', choices=('baseline', 'nominal', 'restore'))
args = parser.parse_args()
if args.phase != 'restore':
    raise SystemExit('TRIAL_RETIRED: inconclusive reset; voltage experiments are disabled')
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/bus/i2c/devices/0-0034').exists()
assert not Path('/sys/bus/i2c/devices/0-0036').exists()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
folder = Path('/var/lib/tzx/diagnostics/dram-rail')
folder.mkdir(parents=True, exist_ok=True)
lock = (folder/'lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
state_path = folder/(boot+'.json')


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
    tx = C.create_string_buffer(bytes([reg]))
    rx = C.create_string_buffer(1)
    transaction((Msg*2)(Msg(addr, 0, 1, C.addressof(tx)),
                         Msg(addr, 1, 1, C.addressof(rx))))
    return rx.raw[0]


def set_dcdc3(value):
    assert 0xbc <= value <= 0xc6 and value & 0x80
    tx = C.create_string_buffer(bytes([0x85, value]))
    transaction((Msg*1)(Msg(0x34, 0, 2, C.addressof(tx))))
    time.sleep(0.005)
    assert read(0x34, 0x85) == value
    print('DRAM_RAIL_STEP_READBACK', hex(value), 500+10*(value & 0x7f), flush=True)


def ramp(destination):
    current = read(0x34, 0x85)
    assert 0xbc <= current <= 0xc6 and destination in (0xbc, 0xc6)
    step = 1 if destination > current else -1
    for value in range(current+step, destination+step, step):
        set_dcdc3(value)
    assert read(0x34, 0x85) == destination


def snapshot():
    return {'axp717': {hex(r): hex(read(0x34, r))
                       for r in (0x80, 0x83, 0x84, 0x85, 0x86, 0x90, 0x91, *range(0x93, 0xa0))},
            'axp323': {hex(r): hex(read(0x36, r)) for r in (0x03, 0x10, *range(0x13, 0x18))}}


def store_state(state):
    tmp = state_path.with_suffix('.tmp')
    with tmp.open('w') as output:
        json.dump(state, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    tmp.replace(state_path)
    fd = os.open(folder, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def restore():
    if not state_path.exists():
        print('DRAM_RAIL_NO_STATE_NO_WRITE', boot, flush=True)
        return
    state = json.loads(state_path.read_text())
    assert state['boot_id'] == boot and state['original_register_0x85'] == 0xbc
    ramp(0xbc)
    print('DRAM_RAIL_ORIGINAL_RESTORED', hex(read(0x34, 0x85)), flush=True)


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
assert read(0x36, 0x03) == 0x49
assert read(0x34, 0x80) == 0x0f
assert [read(0x34, r) for r in (0x83, 0x84, 0x85, 0x86, 0x98)] == [0xa8, 0xa8, 0xbc, 0x00, 0x0d]
binary = Path('/home/debian/library-copy-coherency-v8')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '342d0c7e9bb52e84bfda236629d08382ea350c2abb35e4c2e7a320204e5ee517'
prefix = '/home/debian/copy-dram-rail-'+args.phase+'-v8'
assert not list(Path('/home/debian').glob(Path(prefix).name+'-*'))
seconds = 60 if args.phase == 'baseline' else 300
state = {'boot_id': boot, 'original_register_0x85': 0xbc,
         'board_rail_mapping': 'reference_inference_not_measured', 'before': snapshot()}
if state_path.exists():
    prior = json.loads(state_path.read_text())
    assert prior['boot_id'] == boot and prior['original_register_0x85'] == 0xbc
store_state(state)
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
env = {k: v for k, v in os.environ.items() if k not in ('TZX_COPY_HIGH_TARGETS', 'TZX_COPY_LOW_TARGETS')}
env['TZX_COPY_HIGH_TARGETS'] = '1'
print('DRAM_RAIL_DIAGNOSTIC_BEGIN', json.dumps({'boot_id': boot, 'phase': args.phase,
      'seconds': seconds, 'full_RAM_bytes': 1 << 32, 'ordinary_libc_no_added_DSB': True,
      'original_BL31': True, 'before': state['before']}), flush=True)
try:
    if args.phase == 'nominal':
        ramp(0xc6)
    expected = 0xc6 if args.phase == 'nominal' else 0xbc
    assert read(0x34, 0x85) == expected
    result = subprocess.run([str(binary), str(seconds), prefix, '255', 'libc'], env=env, timeout=seconds+35)
    assert read(0x34, 0x85) == expected
    print('DRAM_RAIL_COPY_RESULT', json.dumps({'phase': args.phase, 'returncode': result.returncode,
          'register_0x85': hex(expected), 'setpoint_mV': 500+10*(expected & 0x7f)}), flush=True)
    state['result'] = {'phase': args.phase, 'returncode': result.returncode, 'after': snapshot()}
    store_state(state)
finally:
    restore()
raise SystemExit(result.returncode)
