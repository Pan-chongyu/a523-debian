"""Archive retained GP1..3 and arm the temporary pinned-loader reset log."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

def read_exact_board_toc0(fd):
    head = os.pread(fd, 32, 256*512)
    assert len(head) == 32 and head[:8] == b'TOC0.GLH'
    length = int.from_bytes(head[28:32], 'little')
    assert length in (40960, 49152)
    data = os.pread(fd, length, 256*512)
    assert len(data) == length
    return data

parser = argparse.ArgumentParser()
parser.add_argument('--live', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert int(Path('/proc/sys/kernel/tainted').read_text()) in (0, 4096)
assert '# CONFIG_RTC_NVMEM is not set' in Path('/boot/config-' + os.uname().release).read_text()
assert {p.name for p in Path('/sys/bus/nvmem/devices').iterdir()} == {'sunxi-sid0'}
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    assert hashlib.sha256(read_exact_board_toc0(fd)).hexdigest() in ('ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df', '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75', '4d1b90298dfc6238ea579eab33f7ca168639f5c512c9bddfeb61c1764118c842', '70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0', '4ae89856592e7b95fde5d0b40e49a09255f9745470fa9cc22bc64a06319ac4bc', '319cdcc46804ce7136b5f00479dd6c320bc561340ea285655293de3665ab179e', '50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b', '1c2ce9324aae67cf5747c36249db0785c74d52c4094e4e735e37217f60800b41', '367d51b493c2c647e12cfb24264afcac714cebcaa8b4605301620211f0befa1c', '09f4028fff214369e301e087c59d4c1dc359e0ee774e19556e73aa867845b0ca')
finally:
    os.close(fd)
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
cookie = int.from_bytes(hashlib.sha256(boot.encode('ascii')).digest()[:8], 'little')
root = Path('/home/debian/tzx-reset-debug')
root.mkdir(mode=0o700, exist_ok=True)
last_path = root / 'rtc-last-armed.json'
last = json.loads(last_path.read_text()) if last_path.exists() else None
if args.live:
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x07090000) as view:
            # Copying a 12-byte MMIO slice can issue an unaligned 64-bit load
            # at GP1. Read each naturally aligned 32-bit device word instead.
            data = struct.pack('<3I', *(struct.unpack_from('<I', view, offset)[0]
                                      for offset in (0x104, 0x108, 0x10c)))
    finally:
        os.close(fd)
else:
    assert not Path('/sys/module/tzx_rtc_log').exists()
    module = Path(__file__).with_name('tzx_rtc_log.ko')
    assert hashlib.sha256(module.read_bytes()).hexdigest() == 'bb446382bdfec6fb87120540f67bd521851149538547f3c162697a2bb9eb22bb'
    subprocess.run(['insmod', str(module), 'boot_cookie=' + str(cookie)], check=True, timeout=15)
    data = Path('/sys/kernel/tzx_rtc_log/previous').read_bytes()
assert len(data) == 12
metadata, value_low, value_high = struct.unpack('<3I', data)
value = value_low | (value_high << 32)
reason = metadata & 0xff
valid = metadata & 0xffff0000 == 0x54580000
report = {'boot_id': boot, 'time_unix': time.time(), 'source': 'live' if args.live else 'previous_at_probe',
          'registers': [hex(v) for v in (metadata, value_low, value_high)],
          'valid_signature': valid, 'reason_code': reason if valid else None,
          'reason': {1: 'armed', 2: 'normal_reboot', 3: 'kernel_die', 4: 'kernel_panic', 5: 'kernel_die_pc_lr', 6: 'unloaded'}.get(reason) if valid else None,
          'cpu': (metadata >> 8) & 0xff if valid else None, 'value': hex(value),
          'previous_arm': last,
          'matches_last_cookie': bool(last and value == last['cookie'])}
if valid and reason == 3:
    report['fault_pc'] = hex(value)
if valid and reason == 5:
    report['fault_pc'] = hex(0xffff800000000000 | value_low)
    report['fault_lr'] = hex(0xffff800000000000 | value_high)
from rtc_context_codec import decode_abort_record
context = decode_abort_record((metadata,value_low,value_high))
if context is not None:
    report.update(context)
path = root / (('rtc-live-' if args.live else 'rtc-previous-') + boot + '-' + str(time.time_ns()) + '.json')
with path.open('x', encoding='ascii') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
    stream.flush()
    os.fsync(stream.fileno())
if not args.live:
    state = {'boot_id': boot, 'cookie': cookie, 'armed_at': time.time(), 'module': 'tzx_rtc_log'}
    temporary = last_path.with_suffix('.new')
    with temporary.open('w', encoding='ascii') as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(last_path)
print('RTC_RESET_CAPTURE', str(path), json.dumps(report), flush=True)
