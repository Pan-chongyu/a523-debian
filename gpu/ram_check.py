#!/usr/bin/env python3
"""Bounded anonymous-RAM integrity load; never accesses a block device. MIT."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import signal
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mib', type=int, default=512)
    p.add_argument('--stop-file', type=Path)
    args = p.parse_args()
    if not 64 <= args.mib <= 768:
        p.error('RAM allocation must be 64..768 MiB')
    alive = True

    def stop(*_):
        nonlocal alive
        alive = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    size = args.mib * 1024 * 1024
    block = os.urandom(1024 * 1024)
    expected = hashlib.sha256()
    with mmap.mmap(-1, size) as data:
        for offset in range(0, size, len(block)):
            data[offset:offset+len(block)] = block
            expected.update(block)
        expected = expected.digest()
        cycles, started = 0, time.monotonic()
        print(json.dumps({'status': 'READY', 'allocated_bytes': size}), flush=True)
        while alive and not (args.stop_file and args.stop_file.exists()):
            if hashlib.sha256(data).digest() != expected:
                raise RuntimeError('RAM hash mismatch')
            cycles += 1
            if cycles % 8 == 0:
                print(json.dumps({'status': 'RUNNING', 'cycles': cycles,
                                  'bytes_checked': size * cycles}), flush=True)
            time.sleep(.05)
        print(json.dumps({'status': 'PASS', 'cycles': cycles, 'bytes_checked': size * cycles,
                          'elapsed_s': round(time.monotonic()-started, 3)}), flush=True)


if __name__ == '__main__':
    main()
