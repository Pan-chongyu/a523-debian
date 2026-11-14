#!/usr/bin/env python3
"""Bounded GPU/API/RAM soak with fail-closed health checks. MIT.

Run as root on the adapted board; workloads themselves run as the desktop user.
This does not change clocks, voltage, thermal controls, disk layout or boot files.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
KERNEL_FAILURE = re.compile(
    r'panfrost.*(?:fault|timeout|hang)|\bBUG:|\bOops:|\bSError\b|'
    r'I/O error|EXT4-fs error|Out of memory|Killed process|GPU reset', re.I)


def read(path):
    return Path(path).read_text().strip()


def run(command, timeout=15):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=int, default=3600)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--user', default='debian')
    args = parser.parse_args()
    if not 60 <= args.duration <= 21600 or os.geteuid() != 0:
        parser.error('root is required; duration must be 60..21600 seconds')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', args.user):
        parser.error('invalid workload user')
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    boot = read('/proc/sys/kernel/random/boot_id')
    user = ['runuser', '-u', args.user, '--']
    baseline_xorg = run(['pgrep', '-x', 'Xorg'])
    baseline_failed = run(['systemctl', '--failed', '--no-legend', '--plain'])
    if baseline_failed:
        raise RuntimeError('Failed units exist before test: ' + baseline_failed)
    if int(read('/proc/sys/kernel/tainted')) != 4096:
        raise RuntimeError('Expected only out-of-tree module taint (4096)')
    baseline_mmc = read('/sys/kernel/debug/mmc0/err_stats')
    if any(int(line.rsplit(':', 1)[1]) for line in baseline_mmc.splitlines()):
        raise RuntimeError('eMMC error counters are nonzero before test')
    initial_log = run(['dmesg', '--color=never'])
    if KERNEL_FAILURE.search(initial_log):
        raise RuntimeError('Existing kernel errors must be resolved before qualification')
    baseline_journal = run(['journalctl', '-k', '-n', '0', '--show-cursor', '--no-pager'])
    # Record a cursor after the last kernel message without clearing the ring buffer.
    if '-- cursor: ' not in baseline_journal:
        baseline_journal = run(['journalctl', '-k', '-n', '1', '--show-cursor', '--no-pager'])
    cursor = baseline_journal.rsplit('-- cursor: ', 1)[1].strip()
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    children, streams = {}, {}
    counts = {'opencl': 0, 'gles_compute': 0, 'gles_pixels': 0, 'glmark': 0}
    totals = {'opencl_integer_words': 0, 'opencl_float32_values': 0,
              'opencl_image_pixels': 0, 'opencl_kernels': 0, 'gles_compute_dispatches': 0}
    peaks, frequencies, tasks = {}, {}, {}
    result = {'status': 'RUNNING', 'started_utc': started_utc, 'requested_seconds': args.duration,
              'kernel': run(['uname', '-r']), 'boot_id': boot, 'xorg_pid': baseline_xorg,
              'scope': 'original adapted tablet; finite stress test, not lifetime certification',
              'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in HERE.glob('*.py')}}
    (args.output / 'kernel-before.txt').write_text(initial_log + '\n')
    atomic_json(args.output / 'result.json', result)

    def launch(name, command):
        stream = (args.output / (name + '.current.log')).open('w')
        streams[name] = stream
        environment = dict(os.environ)
        environment.update(DISPLAY=':0', XAUTHORITY=f'/home/{args.user}/.Xauthority')
        # Alternate uncached and cached compilation without changing the desktop's environment.
        if name in ('gles_compute', 'gles_pixels') and counts[name] % 2 == 0:
            environment['MESA_SHADER_CACHE_DISABLE'] = 'true'
        children[name] = subprocess.Popen(user + command, stdout=stream, stderr=subprocess.STDOUT,
                                          env=environment, start_new_session=True)
        tasks[name] = time.monotonic()

    def consume(name):
        child = children[name]
        if child.poll() is None:
            if time.monotonic() - tasks[name] > (150 if name == 'glmark' else 60):
                raise RuntimeError(name + ' test timed out')
            return False
        streams[name].close()
        output = (args.output / (name + '.current.log')).read_text(errors='replace')
        with (args.output / (name + '.jsonl')).open('a') as log:
            log.write(json.dumps({'iteration': counts[name] + 1, 'returncode': child.returncode,
                                  'output': output}, ensure_ascii=False) + '\n')
        if child.returncode:
            raise RuntimeError(f'{name} exit {child.returncode}: {output[-3000:]}')
        if name == 'opencl':
            parsed = json.loads(output)
            if parsed['status'] != 'PASS' or parsed['device_type'] != 4 or parsed['cpu_fallback']:
                raise RuntimeError('OpenCL test did not qualify the GPU')
            for target, source in (('opencl_integer_words', 'integer_words'),
                                   ('opencl_float32_values', 'float32_values'),
                                   ('opencl_image_pixels', 'rgba_image_pixels'),
                                   ('opencl_kernels', 'kernels')):
                totals[target] += parsed[source]
        elif name == 'gles_compute':
            if 'MALI_G57_COMPUTE_ALL_WORDS_PASS' not in output:
                raise RuntimeError('Missing GLES compute verification')
            totals['gles_compute_dispatches'] += 32
        elif name == 'gles_pixels':
            if 'GPU_SHADER_AND_PIXEL_READBACK_PASS' not in output or 'Mali-G57' not in output:
                raise RuntimeError('Missing native GLES pixel verification')
        elif name == 'glmark':
            if 'Mali-G57 (Panfrost)' not in output or 'glmark2 Score:' not in output or 'Error:' in output:
                raise RuntimeError('glmark2 did not finish on Panfrost')
        counts[name] += 1
        return True

    def health():
        if read('/proc/sys/kernel/random/boot_id') != boot:
            raise RuntimeError('Unexpected reboot')
        if int(read('/proc/sys/kernel/tainted')) != 4096:
            raise RuntimeError('New kernel taint')
        if read('/sys/kernel/debug/mmc0/err_stats') != baseline_mmc:
            raise RuntimeError('New eMMC errors')
        for path in ('/sys/module/tzx_gpu_devfreq_guard/parameters/fault',
                     '/sys/module/tzx_emmc_hs_lease/parameters/fault',
                     '/sys/module/tzx_display/parameters/screen_buffer_errors',
                     '/sys/module/tzx_display/parameters/screen_panel_errors'):
            if int(read(path)):
                raise RuntimeError('Hardware guard/error counter: ' + path)
        temps = {}
        for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
            name, value = read(zone / 'type'), int(read(zone / 'temp'))
            if not 0 < value < 85000:
                raise RuntimeError(f'Temperature stop: {name}={value}')
            temps[name] = value
            peaks[name] = max(peaks.get(name, 0), value)
        required = {'gpu-thermal', 'cpu-big-thermal', 'cpu-little-thermal',
                    'npu-thermal', 'ddr-thermal'}
        if not required.issubset(temps):
            raise RuntimeError('Missing physical thermal sensors: ' + str(required - temps.keys()))
        gpu = int(read('/sys/class/devfreq/1800000.gpu/cur_freq'))
        frequencies[str(gpu)] = frequencies.get(str(gpu), 0) + 1
        if not 150000000 <= gpu <= 600000000:
            raise RuntimeError('GPU frequency outside qualified envelope')
        if children['ram'].poll() is not None:
            raise RuntimeError('RAM integrity worker stopped unexpectedly')
        if run(['pgrep', '-x', 'Xorg']) != baseline_xorg:
            raise RuntimeError('Desktop X server restarted')
        if run(['systemctl', '--failed', '--no-legend', '--plain']):
            raise RuntimeError('A systemd unit failed')
        current_log = run(['dmesg', '--color=never'])
        if KERNEL_FAILURE.search(current_log):
            raise RuntimeError('Kernel GPU/memory/storage fault: ' +
                               '\n'.join(s for s in current_log.splitlines() if KERNEL_FAILURE.search(s)))
        return {'elapsed_s': round(time.monotonic() - started, 3), 'temperatures_mc': temps,
                'gpu_hz': gpu, 'counts': dict(counts),
                'cpu_khz': {p.name: int(read(p / 'scaling_cur_freq'))
                            for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*')},
                'memory_available_kib': int(next(s.split()[1] for s in read('/proc/meminfo').splitlines()
                                                  if s.startswith('MemAvailable:')))}

    commands = {
        'opencl': lambda: ['python3', str(HERE / 'opencl_check.py'), '--seed', str(counts['opencl'] + 1)],
        'gles_compute': lambda: ['python3', str(HERE / 'gles_compute.py')],
        'gles_pixels': lambda: ['python3', str(HERE / 'gles_pixels.py'), '--node',
                               '/dev/dri/by-path/platform-tzx-de-scanout-card'],
        'glmark': lambda: ['glmark2-es2', '--off-screen', '--size', '640x480',
                           '-b', 'build:duration=2', '-b', 'texture:duration=2',
                           '-b', 'shading:duration=2', '-b', 'bump:duration=2',
                           '-b', 'conditionals:duration=2', '-b', 'terrain:duration=2'],
    }
    try:
        launch('ram', ['python3', str(HERE / 'ram_check.py'), '--mib', '512',
                       '--stop-file', str(args.output / 'ram.stop')])
        for name, command in commands.items():
            launch(name, command())
        next_sample = started
        while time.monotonic() - started < args.duration:
            for name, command in commands.items():
                if consume(name):
                    launch(name, command())
            if time.monotonic() >= next_sample:
                sample = health()
                with (args.output / 'samples.jsonl').open('a') as log:
                    log.write(json.dumps(sample, sort_keys=True) + '\n')
                result.update(elapsed_s=sample['elapsed_s'], counts=dict(counts), totals=dict(totals),
                              temperature_peaks_mc=dict(peaks), gpu_frequency_samples=dict(frequencies))
                atomic_json(args.output / 'result.json', result)
                print(json.dumps(sample), flush=True)
                next_sample += 5
            time.sleep(.15)
        # Let the last submitted jobs finish and validate their results; never hide an active failure.
        for name in commands:
            children[name].wait(timeout=150)
            consume(name)
        health()
        (args.output / 'ram.stop').touch()
        children['ram'].wait(timeout=30)
        streams['ram'].close()
        ram_lines = (args.output / 'ram.current.log').read_text().splitlines()
        ram_result = json.loads(ram_lines[-1])
        if children['ram'].returncode or ram_result['status'] != 'PASS':
            raise RuntimeError('RAM worker final verification failed')
        result.update(status='PASS', ram=ram_result, counts=dict(counts), totals=dict(totals),
                      xorg_pid_unchanged=True, new_kernel_errors=0, new_mmc_errors=0)
    except BaseException as error:
        result.update(status='FAIL', error=repr(error), counts=dict(counts), totals=dict(totals))
        raise
    finally:
        for child in children.values():
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=10)
        for stream in streams.values():
            stream.close()
        result.update(elapsed_s=round(time.monotonic() - started, 3),
                      ended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                      temperature_peaks_mc=dict(peaks), gpu_frequency_samples=dict(frequencies))
        atomic_json(args.output / 'result.json', result)
        (args.output / 'kernel-after.txt').write_text(run(['dmesg', '--color=never']) + '\n')
        (args.output / 'kernel-delta.txt').write_text(run(
            ['journalctl', '-k', '--after-cursor', cursor, '--no-pager']) + '\n')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
