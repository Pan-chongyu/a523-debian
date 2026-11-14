#!/usr/bin/env python3
"""Repeat OpenCL C 3.0 and IL tests with fresh GPU contexts, stopping on error. MIT."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cycles', type=int, default=100)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not 1 <= args.cycles <= 1000:
        p.error('cycles must be 1..1000')
    if args.output.exists():
        p.error('choose a new output file')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    here, started = Path(__file__).resolve().parent, time.monotonic()
    result = dict(status='RUNNING', requested_cycles=args.cycles, cycles=0,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        started_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    totals = dict(int64_values=0, global_atomics=0, read_write_image_pixels=0, spirv_words=0)
    try:
        for cycle in range(args.cycles):
            for name in ('opencl_extended.py', 'spirv_check.py'):
                child = subprocess.run([sys.executable, str(here / name)], text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
                if child.returncode:
                    raise RuntimeError(f'{name} exit {child.returncode}: {child.stdout[-2000:]}')
                check = json.loads(child.stdout)
                if check['status'] != 'PASS' or check['cpu_fallback'] or check['device_type'] != 4:
                    raise RuntimeError('Invalid GPU result: ' + name)
                if name == 'opencl_extended.py':
                    for key in ('int64_values', 'global_atomics', 'read_write_image_pixels'):
                        totals[key] += check[key]
                else:
                    totals['spirv_words'] += check['words_checked']
                with args.output.with_suffix('.jsonl').open('a') as log:
                    log.write(json.dumps(dict(cycle=cycle+1, test=name, result=check)) + '\n')
            result.update(cycles=cycle+1, totals=dict(totals), elapsed_s=round(time.monotonic()-started, 3))
            args.output.write_text(json.dumps(result, indent=2) + '\n')
        result['status'] = 'PASS'
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        result.update(elapsed_s=round(time.monotonic()-started, 3),
                      ended_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
