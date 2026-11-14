"""Stop a GPU comparison immediately if resident library or loader checks fail."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--label', required=True)
parser.add_argument('--aarch64-pgtable', action='store_true')
parser.add_argument('--keep-awake', action='store_true')
args = parser.parse_args()
assert args.label and all(c.isalnum() or c == '-' for c in args.label)
assert os.geteuid() == 0
ready = Path('/run/tzx-library-pages-' + args.label + '.ready')
assert not ready.exists()
stage_file = Path('/home/debian/gpu-guarded-' + args.label + '-stages.jsonl')
assert not stage_file.exists()


def phase(name, **fields):
    row = dict(phase=name, monotonic=time.monotonic(),
               boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), **fields)
    with stage_file.open('a') as stream:
        stream.write(json.dumps(row) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    print('GPU_GUARD_STAGE', json.dumps(row), flush=True)


phase('before-library-watch', aarch64_page_tables=args.aarch64_pgtable,
      runtime_autosuspend_disabled=args.keep_awake)
watch = subprocess.Popen(['python3', '/home/debian/watch_library_pages.py',
                           '--seconds', '890', '--label', args.label])
trial = None
try:
    deadline = time.monotonic() + 50
    while not ready.exists():
        assert watch.poll() is None, 'Library reference setup failed'
        assert time.monotonic() < deadline, 'Library reference setup deadline'
        time.sleep(0.2)
    phase('library-watch-ready')
    command = ['python3', '/home/debian/run_gpu_dma32_desktop_trial.py', '--trial-id',
               args.label, '--log-prefix', 'gpu-guarded-' + args.label]
    if args.aarch64_pgtable:
        command.append('--aarch64-pgtable')
    if args.keep_awake:
        command.append('--keep-awake')
    phase('before-gpu-trial')
    trial = subprocess.Popen(command, start_new_session=True)
    deadline = time.monotonic() + 750
    while trial.poll() is None:
        assert watch.poll() is None and ready.exists(), 'Resident library/loader guard failed'
        assert time.monotonic() < deadline, 'Guarded trial deadline'
        time.sleep(0.5)
    assert trial.returncode == 0, ('GPU trial failed', trial.returncode)
    phase('gpu-trial-completed')
    assert watch.poll() is None and ready.exists(), 'Library guard ended early'
    watch.send_signal(signal.SIGUSR1)
    assert watch.wait(timeout=20) == 0
    phase('library-watch-clean-stop')
    report = {'label': args.label, 'gpu_suites_and_resident_library_guard': 'PASS',
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'aarch64_page_table_comparison': args.aarch64_pgtable,
              'runtime_autosuspend_disabled': args.keep_awake,
              'persistent_gpu_enablement': False}
    Path('/home/debian/gpu-guarded-' + args.label + '.json').write_text(json.dumps(report, indent=2) + '\n')
    print('GPU_FULL_COMBINED_AND_RESIDENT_LIBRARY_GUARD_PASS', json.dumps(report), flush=True)
finally:
    if trial is not None and trial.poll() is None:
        os.killpg(trial.pid, signal.SIGTERM)
        try:
            trial.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(trial.pid, signal.SIGKILL)
            trial.wait()
    if watch.poll() is None:
        watch.terminate()
        watch.wait(timeout=8)
