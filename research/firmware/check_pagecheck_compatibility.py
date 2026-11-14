"""Check the one changed public layout before using existing board modules."""
import json
from pathlib import Path
import subprocess
import struct

assert '#5 ' in subprocess.check_output(['uname', '-v'], text=True)
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
roots = [Path('/lib/modules/7.3.3-tzx-a523-accel1'), Path('/usr/local/lib')]
modules = sorted({p.resolve() for root in roots for p in root.rglob('*.ko')})
changed_layout_users = []
for path in modules:
    data = path.read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01', path
    section_offset = struct.unpack_from('<Q', data, 40)[0]
    stride, count = struct.unpack_from('<HH', data, 58)
    assert stride == 64
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, section_offset+i*stride)
                for i in range(count)]
    undefined = set()
    tables = [s for s in sections if s[1] == 2]
    assert tables, path
    for section in tables:
        strings = sections[section[6]]
        names = data[strings[4]:strings[4]+strings[5]]
        assert section[9] == 24
        for offset in range(section[4], section[4]+section[5], 24):
            name, _, _, index, _, _ = struct.unpack_from('<IBBHQQ', data, offset)
            if index == 0 and name:
                undefined.add(names[name:names.index(b'\0', name)].decode('ascii'))
    if 'mem_section' in undefined:
        changed_layout_users.append(str(path))
report = {'modules_checked': len(modules), 'mem_section_layout_users': changed_layout_users,
          'scope': 'PAGE_EXTENSION doubles mem_section; other enabled options add checks, not board-facing structure fields'}
print('PAGECHECK_EXISTING_MODULE_LAYOUT_CHECK', json.dumps(report), flush=True)
assert modules and not changed_layout_users, 'Rebuild these modules against #6 before boot'
print(Path('/proc/cmdline').read_text(), flush=True)
subprocess.run(['systemctl', 'cat', 'tzx-cpub.service'], check=True)
