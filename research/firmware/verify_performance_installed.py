"""Qualification of actual production service recovery, load and file integrity."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/home/debian/performance-installed')
ROOT.mkdir(exist_ok=True)
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
CPU = 'tzx-cpu-performance.service'
GPU = 'tzx-gpu-performance.service'
peaks = {}
events = []
started = time.monotonic()
children = []
original_xorg = subprocess.check_output(['pgrep', '-x', 'Xorg'], text=True).strip()

def run(*command, timeout=100):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    assert result.returncode == 0, (command, result.returncode, result.stdout[-2000:])
    return result.stdout

def sample():
    assert time.monotonic()-started < 600
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    assert run('pgrep', '-x', 'Xorg').strip() == original_xorg, 'Desktop restarted'
    errors = [s for s in run('dmesg').splitlines()
              if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b', s, re.I)]
    assert not errors, errors
    for p in Path('/sys/class/thermal').glob('thermal_zone*'):
        name, value = (p/'type').read_text().strip(), int((p/'temp').read_text())
        assert 0 < value < 70000, (name, value)
        peaks[name] = max(peaks.get(name, 0), value)
    for name in ('screen_buffer_errors', 'screen_panel_errors'):
        assert int((Path('/sys/module/tzx_display/parameters')/name).read_text()) == 0, name
    assert int(Path('/sys/module/tzx_cpufreq_safepll/parameters/clock_fault').read_text()) == 0

def wait_active(kind):
    p = Path('/run/tzx-'+kind+'-performance.json')
    for attempt in range(100):
        if p.exists():
            state = json.loads(p.read_text())
            if state['boot_id'] == BOOT and state['state'] == 'active':
                return state
        time.sleep(0.25)
    raise RuntimeError(kind+' performance service did not become ready')

def workload(command, name, timeout=240):
    with (ROOT/(name+'.log')).open('w') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        children.append(process)
        limit = time.monotonic()+timeout
        while process.poll() is None:
            sample()
            assert time.monotonic() < limit, name
            time.sleep(1)
        assert process.returncode == 0, (name, process.returncode)
    return (ROOT/(name+'.log')).read_text()

try:
    # SIGKILL bypasses Python finally: systemd ExecStopPost must restore both
    # baseline CPU services and make subsequent startup independently work.
    run('systemctl', 'kill', '--kill-whom=main', '--signal=SIGKILL', CPU)
    for attempt in range(100):
        if not Path('/sys/module/tzx_cpufreq_safepll').exists():
            if subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-cpu-cooling.service']).returncode == 0:
                break
        time.sleep(0.25)
    else:
        raise AssertionError('Killed CPU controller did not recover baseline')
    assert all(Path('/sys/devices/system/cpu/cpufreq/policy'+str(n)+'/scaling_driver').read_text().strip() == 'tzx-a523-divider' for n in (0,4))
    run('systemctl', 'reset-failed', CPU)
    run('systemctl', 'start', CPU)
    wait_active('cpu')
    events.append('CPU controller SIGKILL: original driver/cooling restored, performance restart PASS')
    run('systemctl', 'stop', GPU)
    assert not Path('/sys/module/tzx_gpu_performance').exists()
    assert int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text()) == 200000000
    run('systemctl', 'start', GPU)
    wait_active('gpu')
    events.append('GPU service stop restores 200MHz; performance restart PASS')
    run('systemctl', 'kill', '--kill-whom=main', '--signal=SIGKILL', GPU)
    for attempt in range(100):
        if not Path('/sys/module/tzx_gpu_performance').exists():
            break
        time.sleep(0.25)
    else:
        raise AssertionError('Killed GPU controller did not restore 200 MHz')
    assert int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text()) == 200000000
    run('systemctl', 'reset-failed', GPU)
    run('systemctl', 'start', GPU)
    wait_active('gpu')
    events.append('GPU controller SIGKILL: systemd restores 200MHz, performance restart PASS')
    sample()
    print('PERFORMANCE_PRODUCTION_RECOVERY_PASS', json.dumps(events), flush=True)
    maximum_cpu = [0, 0]
    maximum_gpu = 0
    for repeat in range(3):
        process = subprocess.Popen(['/home/debian/memory-check-bounded', '2560'],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        children.append(process)
        with (ROOT/('gpu-scenes-'+str(repeat+1)+'.log')).open('w') as stream:
            gpu = subprocess.Popen(['runuser', '-u', 'debian', '--', 'env', 'DISPLAY=:0',
                                    'XAUTHORITY=/home/debian/.Xauthority', 'glmark2-es2',
                                    '--size', '640x480', '--off-screen', '-b', ':duration=1'],
                                   stdout=stream, stderr=subprocess.STDOUT)
            children.append(gpu)
            limit = time.monotonic()+150
            while gpu.poll() is None or process.poll() is None:
                sample()
                for index, cpu in enumerate((0,4)):
                    value = int(Path('/sys/devices/system/cpu/cpufreq/policy'+str(cpu)+'/scaling_cur_freq').read_text())
                    maximum_cpu[index] = max(maximum_cpu[index], value)
                maximum_gpu = max(maximum_gpu, int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text()))
                assert time.monotonic() < limit
                time.sleep(0.5)
            output = process.communicate(timeout=5)[0]
            (ROOT/('memory-2560MiB-'+str(repeat+1)+'.log')).write_text(output)
            assert process.returncode == 0 and 'MEMORY_TEST_2560_MIB_8_THREADS_PASS' in output, output
            assert gpu.returncode == 0
        text = (ROOT/('gpu-scenes-'+str(repeat+1)+'.log')).read_text()
        assert 'Mali-G57 (Panfrost)' in text and 'Error:' not in text
        score = int(re.search(r'glmark2 Score:\s*(\d+)', text)[1])
        events.append({'combined_cycle': repeat+1, 'score': score, 'memory_mib': 2560})
        print('PERFORMANCE_COMBINED_LOAD_PASS', json.dumps(events[-1]), flush=True)
    assert maximum_cpu == [792000, 1008000], maximum_cpu
    assert maximum_gpu == 600000000, maximum_gpu
    audit = workload(['python3', '/home/debian/verify_safe_memory.py', '--files-only'], 'file-audit')
    assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
    sample()
    env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/home/debian/.Xauthority')
    xrandr = subprocess.check_output(['runuser', '-u', 'debian', '--', 'xrandr', '--query'], env=env, text=True)
    assert 'current 1280 x 800' in xrandr and ' right (' in xrandr
    glx = subprocess.check_output(['runuser', '-u', 'debian', '--', 'glxinfo', '-B'], env=env, text=True)
    assert 'Mali-G57' in glx and 'Accelerated: yes' in glx
    failed = subprocess.check_output(['systemctl', '--failed', '--no-legend', '--plain'], text=True)
    assert not failed.strip(), failed
    for kind in ('cpu','gpu'):
        wait_active(kind)
    record = {'status': 'PASS', 'boot_id': BOOT, 'xorg_pid_unchanged': original_xorg,
              'events': events, 'actual_cpu_maximum_khz': maximum_cpu, 'actual_gpu_maximum_hz': maximum_gpu,
              'peaks_mc': peaks, 'xrandr': xrandr, 'glx': glx, 'mapped_files_audit': audit,
              'failed_units': [], 'screen_errors': 0, 'kernel_taint': 4096,
              'elapsed': round(time.monotonic()-started, 2), 'physical_reboot_tested': False}
    (ROOT/'result.json').write_text(json.dumps(record, indent=2)+'\n')
    Path('/var/lib/tzx/performance-installed-validation.json').write_text(json.dumps(record, indent=2)+'\n')
    print('PERFORMANCE_INSTALLED_VALIDATION_PASS', json.dumps(record), flush=True)
finally:
    for child in children:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
