#!/usr/bin/env python3
"""Small persistent GPU health recorder; never changes clocks or resets devices. MIT."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time

from soak import KERNEL_FAILURE

DIRECTORY = Path('/var/lib/tzx-gpu-api-health')
RUNTIME = Path('/run/tzx-gpu-api-health.json')


def atomic(path, record, persistent=False):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as f:
        json.dump(record, f, sort_keys=True, indent=2)
        f.write('\n'); f.flush()
        if persistent:
            os.fsync(f.fileno())
    temporary.chmod(0o600 if persistent else 0o644)
    temporary.replace(path)


def notify(message):
    address = os.environ.get('NOTIFY_SOCKET')
    if address:
        if address.startswith('@'):
            address = '\0' + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address); sock.sendall(message.encode())


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run through tzx-gpu-api-health.service')
    DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    previous = None
    last = DIRECTORY / 'latest.json'
    if last.exists():
        previous = json.loads(last.read_text())
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    sentinel = os.urandom(4 * 1024 * 1024)
    digest = hashlib.sha256(sentinel).digest()
    same_boot = bool(previous and previous.get('boot_id') == boot)
    peaks = dict(previous.get('temperature_peaks_mc', {})) if same_boot else {}
    samples = 0
    degraded = bool(same_boot and previous.get('had_issue_this_session'))
    record = {'boot_id': boot, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'status': 'STARTING', 'samples': 0,
              'prior_monitor_ended_uncleanly': bool(previous and previous.get('status') != 'STOPPED'),
              'previous_boot_differed': bool(previous and previous.get('boot_id') != boot),
              'unclean_ending_is_not_a_reboot_cause': True}
    if same_boot and previous.get('first_issues'):
        record['first_issues'] = previous['first_issues']
        record['first_issue_utc'] = previous['first_issue_utc']
    next_persist = 0
    try:
        while not stop.is_set():
            issues = []
            if hashlib.sha256(sentinel).digest() != digest:
                issues.append('small RAM sentinel mismatch')
            try:
                taint = int(Path('/proc/sys/kernel/tainted').read_text())
                if taint != 4096:
                    issues.append('unexpected kernel taint: ' + str(taint))
                for path in ('/sys/module/tzx_gpu_devfreq_guard/parameters/fault',
                             '/sys/module/tzx_emmc_hs_lease/parameters/fault',
                             '/sys/module/tzx_display/parameters/screen_buffer_errors',
                             '/sys/module/tzx_display/parameters/screen_panel_errors'):
                    value = int(Path(path).read_text())
                    if value:
                        issues.append(Path(path).parent.parent.name + '/' + Path(path).name + '=' + str(value))
                temps = {}
                for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
                    name, value = (zone / 'type').read_text().strip(), int((zone / 'temp').read_text())
                    temps[name] = value
                    peaks[name] = max(peaks.get(name, 0), value)
                    if not 0 < value < 85000:
                        issues.append('thermal limit: ' + name + '=' + str(value))
                required = {'gpu-thermal', 'cpu-big-thermal', 'cpu-little-thermal', 'ddr-thermal', 'npu-thermal'}
                if not required.issubset(temps):
                    issues.append('physical thermal sensor missing')
                kernel = subprocess.check_output(['dmesg', '--color=never'], text=True, timeout=10)
                issues.extend(line for line in kernel.splitlines() if KERNEL_FAILURE.search(line))
                gpu = int(Path('/sys/class/devfreq/1800000.gpu/cur_freq').read_text())
                guard = json.loads(Path('/run/tzx-gpu-performance.json').read_text())
                if guard['state'] != 'active' or guard['boot_id'] != boot:
                    issues.append('GPU performance guard is not active on this boot')
                mmc = Path('/sys/kernel/debug/mmc0/err_stats').read_text()
                if any(int(line.rsplit(':', 1)[1]) for line in mmc.splitlines()):
                    issues.append('nonzero eMMC error counter')
                record.update(temperatures_mc=temps, gpu_hz=gpu, taint=taint,
                              gpu_guard=guard['state'])
            except (OSError, KeyError, ValueError, subprocess.SubprocessError) as error:
                issues.append('health read failed: ' + repr(error))
            samples += 1
            degraded |= bool(issues)
            if issues and 'first_issues' not in record:
                record['first_issues'] = list(issues)
                record['first_issue_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
            record.update(status='DEGRADED' if degraded else 'ACTIVE', samples=samples,
                          updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                          uptime_s=round(float(Path('/proc/uptime').read_text().split()[0]), 2),
                          temperature_peaks_mc=dict(peaks), current_issues=issues,
                          had_issue_this_session=degraded)
            atomic(RUNTIME, record)
            now = time.monotonic()
            if now >= next_persist or issues:
                atomic(last, record, persistent=True)
                atomic(DIRECTORY / (boot + '.json'), record, persistent=True)
                # Retain at most 32 boot summaries; leave unrelated logs untouched.
                histories = sorted((p for p in DIRECTORY.glob('*.json') if p.name != 'latest.json'),
                                   key=lambda p: p.stat().st_mtime)
                for path in histories[:-32]:
                    path.unlink()
                next_persist = now + 30
            if samples == 1:
                notify('READY=1')
            notify('WATCHDOG=1\nSTATUS=' + record['status'] + '; samples=' + str(samples))
            if issues:
                print(json.dumps({'status': record['status'], 'issues': issues}), flush=True)
            stop.wait(10)
    finally:
        record.update(status='STOPPED', had_issue_this_session=degraded,
                      stopped_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                      stop_is_not_proof_of_clean_system_shutdown=True)
        atomic(last, record, persistent=True)
        atomic(DIRECTORY / (boot + '.json'), record, persistent=True)
        atomic(RUNTIME, record)


if __name__ == '__main__':
    main()
