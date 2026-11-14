"""Keep read-only library mappings and preserve the first changed cache page."""
import argparse
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import signal
import struct
import subprocess
import time
from tzx_direct_io import read_direct

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=780)
parser.add_argument('--label', required=True)
parser.add_argument('--self-test-capture', action='store_true')
args = parser.parse_args()
assert 1 <= args.seconds <= 900
assert args.label and all(c.isalnum() or c == '-' for c in args.label)
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists(), 'Establish disk references before loading GPU'
root = Path('/home/debian/tzx-gpu-debug/pages-' + args.label)
root.mkdir(mode=0o700, exist_ok=False)


def durable_write(path, data):
    with path.open('w') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def phase(name, **fields):
    row = dict(phase=name, monotonic=time.monotonic(), **fields)
    with (root / 'setup.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    print('LIBRARY_PAGE_SETUP', json.dumps(row), flush=True)


def buffer_address(obj):
    view = BufferInfo()
    assert get_buffer(obj, ctypes.byref(view), 0) == 0
    address = view.buf
    release_buffer(ctypes.byref(view))
    return address


def physical_entry(address):
    with open('/proc/self/pagemap', 'rb', buffering=0) as pagemap:
        pagemap.seek((address // 4096) * 8)
        value = struct.unpack('<Q', pagemap.read(8))[0]
    return {'virtual_address': hex(address), 'physical_page': hex((value & ((1 << 55)-1))*4096),
            'pagemap_entry': hex(value)}


def capture_views(path, mapping, address, cached, expected, offsets):
    """Read the original mapping independently before any sync or disk I/O.

    The first comparison uses a Python copy. Its PFN need not be the PFN of
    the file mapping, so preserve both and avoid attributing copy damage to
    the file page without an independent read.
    """
    copied_address = buffer_address(cached)
    report = {'pid': os.getpid(), 'pages': []}
    pointers = set()
    mem = os.open('/proc/self/mem', os.O_RDONLY)
    try:
        for offset in offsets:
            length = min(4096, len(expected) - offset)
            initial = cached[offset:offset+length]
            original = os.pread(mem, length, address + offset)
            copied = os.pread(mem, length, copied_address + offset)
            repeat = mapping[offset:offset+length]
            stem = root / ('page-' + format(offset, 'x'))
            Path(str(stem) + '-proc-mapping.bin').write_bytes(original)
            Path(str(stem) + '-proc-copy.bin').write_bytes(copied)
            Path(str(stem) + '-repeat-mapping.bin').write_bytes(repeat)
            for pos in range(0, len(initial)-7, 8):
                if initial[pos:pos+8] != expected[offset+pos:offset+pos+8]:
                    value = struct.unpack_from('<Q', initial, pos)[0]
                    if 0x100000000 <= value < 0x1000000000000:
                        pointers.add(value)
            report['pages'].append({
                'offset': offset,
                'mapping_before': physical_entry(address + offset),
                'copy_before': physical_entry(copied_address + offset),
                # Python bytes payloads need not be page aligned. A changed
                # line late in this logical page may reside in the next PFN.
                'changed_cachelines': [
                    {'file_offset': offset + pos,
                     'mapping': physical_entry(address + offset + pos),
                     'copy': physical_entry(copied_address + offset + pos)}
                    for pos in range(0, length, 64)
                    if initial[pos:pos+64] != expected[offset+pos:offset+pos+64]
                ],
                'proc_mapping_matches_expected': original == expected[offset:offset+length],
                'proc_mapping_matches_first_copy': original == initial,
                'proc_copy_matches_first_copy': copied == initial,
                'repeat_mapping_matches_expected': repeat == expected[offset:offset+length],
            })
    finally:
        os.close(mem)
    (root / 'monitor-maps.txt').write_text(Path('/proc/self/maps').read_text())
    matches = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            rows = (proc / 'maps').read_text().splitlines()
            found = []
            for row in rows:
                lo, hi = (int(n, 16) for n in row.split()[0].split('-'))
                hits = sorted(hex(value) for value in pointers if lo <= value < hi)
                if hits:
                    found.append({'map': row, 'values': hits})
            if found:
                matches.append({'pid': int(proc.name), 'comm': (proc / 'comm').read_text().strip(),
                                'matches': found})
        except (OSError, ValueError):
            continue
    report['candidate_pointer_mappings'] = matches
    report['path'] = str(path)
    return report


phase('started', boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
paths = {Path('/usr/bin/journalctl'), Path('/usr/bin/systemctl')}
paths.update(Path('/usr/lib/aarch64-linux-gnu') / name for name in (
    'libcrypto.so.3', 'libc.so.6', 'libsystemd.so.0', 'libpcre2-8.so.0',
    'ld-linux-aarch64.so.1', 'libmount.so.1', 'libglib-2.0.so.0', 'libgio-2.0.so.0'))
paths = sorted({path.resolve(strict=True) for path in paths})


class BufferInfo(ctypes.Structure):
    _fields_ = [('buf', ctypes.c_void_p), ('obj', ctypes.c_void_p),
                ('length', ctypes.c_ssize_t), ('itemsize', ctypes.c_ssize_t),
                ('readonly', ctypes.c_int), ('ndim', ctypes.c_int),
                ('format', ctypes.c_void_p), ('shape', ctypes.c_void_p),
                ('strides', ctypes.c_void_p), ('suboffsets', ctypes.c_void_p),
                ('internal', ctypes.c_void_p)]


get_buffer = ctypes.pythonapi.PyObject_GetBuffer
get_buffer.argtypes = [ctypes.py_object, ctypes.POINTER(BufferInfo), ctypes.c_int]
get_buffer.restype = ctypes.c_int
release_buffer = ctypes.pythonapi.PyBuffer_Release
release_buffer.argtypes = [ctypes.POINTER(BufferInfo)]
entries = []
for path in paths:
    phase('reference-start', path=str(path))
    expected = read_direct(path)
    assert path.read_bytes() == expected, ('Baseline cache differs', str(path))
    # An executable opened for writing would block execve with ETXTBSY.
    stream = path.open('rb', buffering=0)
    mapping = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
    view = BufferInfo()
    assert get_buffer(mapping, ctypes.byref(view), 0) == 0 and view.readonly
    address = view.buf
    release_buffer(ctypes.byref(view))
    entries.append((path, stream, mapping, address, expected))
    phase('reference-ready', path=str(path), bytes=len(expected))
metadata = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'files': {str(path): hashlib.sha256(expected).hexdigest()
                      for path, _, _, _, expected in entries},
            'read_only_access': True, 'cpu_frequency_or_voltage_changed': False}
metadata['monitor_pid'] = os.getpid()
metadata['mapping_addresses'] = {str(path): hex(address) for path, _, _, address, _ in entries}
durable_write(root / 'baseline.json', json.dumps(metadata, indent=2) + '\n')
ready = Path('/run/tzx-library-pages-' + args.label + '.ready')
durable_write(ready, str(root) + '\n')
phase('ready')
print('LIBRARY_PAGE_WATCH_READY', str(root), len(entries), flush=True)
started = time.monotonic()
iteration = 0
requested_stop = False


def request_stop(signum, frame):
    global requested_stop
    requested_stop = True


signal.signal(signal.SIGUSR1, request_stop)
try:
    if args.self_test_capture:
        # Exercise the failure-only reader with synthetic private RAM. The
        # saved copy is stale while the original mapping has already healed.
        reference = bytes(4096)
        with mmap.mmap(-1, 4096) as sample:
            sample[:] = reference
            sample[3968:] = bytes(range(128))
            copied = sample[:]
            sample[:] = reference
            views = capture_views(Path('/synthetic-private-ram'), sample,
                                  buffer_address(sample), copied, reference, [0])
        page = views['pages'][0]
        assert page['proc_mapping_matches_expected']
        assert not page['proc_mapping_matches_first_copy']
        assert page['proc_copy_matches_first_copy']
        assert page['repeat_mapping_matches_expected']
        views['synthetic_self_test'] = True
        (root / 'self-test-views.json').write_text(json.dumps(views, indent=2) + '\n')
        print('LIBRARY_INDEPENDENT_CAPTURE_SELF_TEST_PASS', flush=True)
        raise SystemExit(0)
    while not requested_stop and time.monotonic() - started < args.seconds:
        for path, _, mapping, address, expected in entries:
            cached = mapping[:]
            if cached == expected:
                continue
            # Preserve independent mapping/copy reads before sync or direct I/O.
            changed_pages = []
            with open('/proc/self/pagemap', 'rb', buffering=0) as pagemap:
                for offset in range(0, len(expected), 4096):
                    if cached[offset:offset+4096] == expected[offset:offset+4096]:
                        continue
                    pagemap.seek(((address+offset)//4096)*8)
                    value = struct.unpack('<Q', pagemap.read(8))[0]
                    changed_pages.append({'offset': offset, 'physical_page': hex((value & ((1 << 55)-1))*4096),
                                          'pagemap_entry': hex(value)})
            views = capture_views(path, mapping, address, cached, expected,
                                  [page['offset'] for page in changed_pages])
            (root / 'independent-views.json').write_text(json.dumps(views, indent=2) + '\n')
            (root / 'changed-cache.bin').write_bytes(cached)
            (root / 'expected.bin').write_bytes(expected)
            report = {'path': str(path), 'elapsed_seconds': time.monotonic() - started,
                      'pages': changed_pages, 'boot_id': metadata['boot_id'],
                      'cached_sha256': hashlib.sha256(cached).hexdigest(),
                      'expected_current_sha256': hashlib.sha256(expected).hexdigest(),
                      'baseline_sha256': metadata['files'][str(path)]}
            (root / 'changed.json').write_text(json.dumps(report, indent=2) + '\n')
            os.sync()
            (root / 'direct-after.bin').write_bytes(read_direct(path))
            print('LIBRARY_PAGE_CHANGE_CAPTURED', json.dumps(report), flush=True)
            raise RuntimeError('Mapped library cache changed')
        if iteration % 10 == 0:
            result = subprocess.run(['journalctl', '-b', '-n', '1', '--no-pager', '--quiet'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=12)
            if result.returncode:
                (root / 'journalctl-stderr.bin').write_bytes(result.stderr)
                (root / 'journalctl-failure.json').write_text(json.dumps({
                    'returncode': result.returncode, 'elapsed_seconds': time.monotonic() - started,
                    'boot_id': metadata['boot_id']}, indent=2) + '\n')
                for path, _, mapping, _, expected in entries:
                    (root / ('failure-' + path.name)).write_bytes(mapping[:])
                os.sync()
                print('LIBRARY_LOADER_SMOKE_FAILED', result.returncode,
                      result.stderr.decode(errors='replace'), flush=True)
                raise RuntimeError('journalctl loader failed')
        iteration += 1
        if iteration % 30 == 0:
            print('LIBRARY_PAGE_WATCH_ALIVE', iteration, round(time.monotonic() - started, 2), flush=True)
        time.sleep(0.25)
    print('LIBRARY_PAGE_WATCH_CLEAN_STOP' if requested_stop else 'LIBRARY_PAGE_WATCH_DURATION_PASS',
          iteration, round(time.monotonic() - started, 2), flush=True)
finally:
    ready.unlink(missing_ok=True)
    for _, stream, mapping, _, _ in entries:
        mapping.close()
        stream.close()
