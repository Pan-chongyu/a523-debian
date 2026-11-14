"""Aligned direct-file reads, including valid partial readv completions."""
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import time


def read_direct(path, expected_sha256=None):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
    try:
        size = os.fstat(fd).st_size
        if not size:
            return b''
        with mmap.mmap(-1, (size + 4095) // 4096 * 4096) as buffer:
            total, completions = 0, []
            while total < size:
                assert total % 512 == 0, ('Unaligned partial direct read', str(path), total)
                view = memoryview(buffer)[total:]
                try:
                    count = os.readv(fd, [view])
                finally:
                    view.release()
                assert count > 0, ('Unexpected EOF', str(path), total, size)
                completions.append(count)
                total += count
                assert total <= size
            data = buffer[:size]
            if len(completions) > 1:
                print('DIRECT_IO_PARTIAL_COMPLETIONS', json.dumps({
                    'path': str(path), 'size': size, 'completions': completions}), flush=True)
            actual = hashlib.sha256(data).hexdigest()
            if expected_sha256 is not None and actual != expected_sha256:
                address = ctypes.addressof(ctypes.c_char.from_buffer(buffer))
                cached = path.read_bytes()
                pages = []
                with open('/proc/self/pagemap', 'rb', buffering=0) as pagemap:
                    for offset in range(0, size, 4096):
                        if data[offset:offset+4096] == cached[offset:offset+4096]:
                            continue
                        pagemap.seek(((address+offset)//4096)*8)
                        entry = struct.unpack('<Q', pagemap.read(8))[0]
                        pages.append({'file_offset': offset,
                                      'physical_page': hex((entry & ((1 << 55)-1))*4096)})
                directory = Path('/home/debian/tzx-gpu-debug/direct-'+str(time.time_ns()))
                directory.mkdir(mode=0o700, parents=True)
                (directory/'direct.bin').write_bytes(data)
                (directory/'cached.bin').write_bytes(cached)
                report = {'path': str(path), 'size': size, 'completions': completions,
                          'expected_sha256': expected_sha256, 'actual_sha256': actual,
                          'cached_sha256': hashlib.sha256(cached).hexdigest(), 'pages': pages}
                (directory/'report.json').write_text(json.dumps(report, indent=2)+'\n')
                print('DIRECT_IO_DATA_MISMATCH_CAPTURE', str(directory), json.dumps({
                    k: v for k, v in report.items() if k != 'pages'}),
                    'different_pages', len(pages), flush=True)
                raise AssertionError(('Direct data differs after complete read', str(path)))
            return data
    finally:
        os.close(fd)
