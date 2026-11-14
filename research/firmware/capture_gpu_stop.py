"""Run inside GDB to preserve the faulting executable page before teardown."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import gdb


def capture_stop():
    inferior = gdb.selected_inferior()
    if not inferior.pid:
        print('GPU_STOP_NO_LIVE_INFERIOR', flush=True)
        return
    pid = inferior.pid
    pc = int(gdb.parse_and_eval('$pc'))
    page = pc & ~4095
    rows = Path(f'/proc/{pid}/maps').read_text().splitlines()
    row = next(r for r in rows if int(r.split('-')[0], 16) <= pc <
               int(r.split()[0].split('-')[1], 16))
    fields = row.split(None, 5)
    start = int(fields[0].split('-')[0], 16)
    offset = int(fields[2], 16) + page - start
    mapped_file = Path(fields[5])
    directory = Path('/home/debian/tzx-gpu-debug')/f'stop-{pid}'
    directory.mkdir(mode=0o700)

    def read_pagemap():
        with open(f'/proc/{pid}/pagemap', 'rb', buffering=0) as stream:
            stream.seek((page//4096)*8)
            value = struct.unpack('<Q', stream.read(8))[0]
        pfn = value & ((1 << 55)-1)
        result = {'entry': hex(value), 'pfn': hex(pfn),
                  'present': bool(value & (1 << 63)),
                  'file_or_shared_anon': bool(value & (1 << 61))}
        if pfn:
            for name in ('kpagecount', 'kpageflags'):
                with open('/proc/'+name, 'rb', buffering=0) as stream:
                    stream.seek(pfn*8)
                    result[name] = struct.unpack('<Q', stream.read(8))[0]
        return result

    before = read_pagemap()
    samples = {'gdb': bytes(inferior.read_memory(page, 4096))}
    fd = os.open(f'/proc/{pid}/mem', os.O_RDONLY)
    try:
        samples['proc_mem'] = os.pread(fd, 4096, page)
    finally:
        os.close(fd)
    fd = os.open(mapped_file, os.O_RDONLY)
    try:
        samples['cached_file'] = os.pread(fd, 4096, offset)
    finally:
        os.close(fd)
    fd = os.open(mapped_file, os.O_RDONLY | os.O_DIRECT)
    try:
        with mmap.mmap(-1, 4096) as buf:
            assert os.preadv(fd, [buf], offset) == 4096
            samples['direct_file'] = buf[:]
    finally:
        os.close(fd)
    after = read_pagemap()
    siginfo = {'raw': str(gdb.parse_and_eval('$_siginfo'))}
    for name in ('si_signo', 'si_errno', 'si_code'):
        siginfo[name] = int(gdb.parse_and_eval('$_siginfo.' + name))
    # Preserve the union interpretation as well as its raw representation.
    # A synthetic SI_USER self-test is distinct from a CPU-generated fault.
    if siginfo['si_code'] > 0:
        siginfo['fault_address'] = hex(int(gdb.parse_and_eval(
            '$_siginfo._sifields._sigfault.si_addr')))
    report = {'pid': pid, 'stop_signal': siginfo['si_signo'], 'siginfo': siginfo,
              'thread_ptid': gdb.selected_thread().ptid,
              'pc': hex(pc), 'page': hex(page), 'mapping': row,
              'file_page_offset': hex(offset), 'pagemap_before': before,
              'pagemap_after': after, 'samples': {}}
    for name, data in samples.items():
        output = directory/(name+'.bin')
        with output.open('wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        diff = [i for i, pair in enumerate(zip(data, samples['direct_file']))
                if pair[0] != pair[1]]
        report['samples'][name] = {
            'sha256': hashlib.sha256(data).hexdigest(),
            'bytes_different_from_disk': len(diff),
            'first_difference': hex(diff[0]) if diff else None,
            'last_difference': hex(diff[-1]) if diff else None,
            'pc_bytes': data[pc-page:pc-page+64].hex(),
        }
    with (directory/'report.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    print('GPU_STOP_PAGE_CAPTURE', json.dumps(report), flush=True)


capture_stop()
