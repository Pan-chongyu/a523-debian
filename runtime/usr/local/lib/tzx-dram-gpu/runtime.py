"""Qualified #5 desktop, pinned to the verified pre-training supply hook."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

def read_exact_board_toc0(fd):
    head = os.pread(fd, 32, 256*512)
    assert len(head) == 32 and head[:8] == b'TOC0.GLH'
    length = int.from_bytes(head[28:32], 'little')
    assert length in (40960, 49152)
    data = os.pread(fd, length, 256*512)
    assert len(data) == length
    return data

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('guard', 'display-start', 'display-stop', 'gpu-start',
                                     'lightdm', 'health', 'fallback'))
a = p.parse_args()
ROOT = Path('/usr/local/lib/tzx-dram-gpu')
MARKER = Path('/var/lib/tzx/gpu-qualified')
PENDING = Path('/var/lib/tzx/dram-gpu-boot-pending.json')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
MODULES = {'panfrost.ko': 'd17b1f2466f70dab017dfd3de2579ddc947a907587422a9d2e7565fccc52fdc8',
           'tzx_display.ko': '49faef93a64f7c4c24dcf330fa8d21c47f9681a848e83bd6716bbfa4643b4440'}


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.is_symlink()
    temporary = path.with_suffix(path.suffix+'.new')
    with temporary.open('w') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fchmod(f.fileno(), 0o600)
        os.fsync(f.fileno())
    temporary.replace(path)
    syncdir(path.parent)


def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def run(*command, timeout=45, **kwargs):
    return subprocess.run(command, check=True, timeout=timeout, **kwargs)


def identity():
    assert os.geteuid() == 0
    assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
    assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == Path('/etc/tzx/device-cid').read_text().strip()


def guard():
    identity()
    assert int(Path('/proc/sys/kernel/tainted').read_text()) in (0, 4096)
    assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
    assert int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1]) > 3900000
    fd = os.open('/dev/mmcblk0', os.O_RDONLY)
    try:
        assert hashlib.sha256(read_exact_board_toc0(fd)).hexdigest() in ('311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75', '4d1b90298dfc6238ea579eab33f7ca168639f5c512c9bddfeb61c1764118c842', '70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0', '4ae89856592e7b95fde5d0b40e49a09255f9745470fa9cc22bc64a06319ac4bc', '319cdcc46804ce7136b5f00479dd6c320bc561340ea285655293de3665ab179e', '50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b', '1c2ce9324aae67cf5747c36249db0785c74d52c4094e4e735e37217f60800b41', '367d51b493c2c647e12cfb24264afcac714cebcaa8b4605301620211f0befa1c', '09f4028fff214369e301e087c59d4c1dc359e0ee774e19556e73aa867845b0ca')
    finally:
        os.close(fd)
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x2e000) as view:
            receipt = [struct.unpack_from('<I', view, i)[0] for i in range(0x80, 0x94, 4)]
            assert receipt[:2] == [0xa523dc03, 1260] and receipt[2] in range(0xbc, 0xca)
            assert receipt[3:] == [0xc9, 2]
    finally:
        os.close(fd)
    voltage = json.loads(subprocess.check_output(['python3', str(ROOT/'read_axp_dram_status.py')], text=True, timeout=15))
    assert voltage['dcdc3_setpoint_mV'] == 1260 and voltage['axp717']['0x85'] == '0xc9'
    for name, digest in MODULES.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    return {'boot_id': BOOT, 'full_4GiB': True, 'voltage_receipt': receipt,
            'actual_setpoint_mV': voltage['dcdc3_setpoint_mV']}


def qualified():
    record = json.loads(MARKER.read_text())
    assert record['profile'] == 'dram-trained-1260-full4g-dma32-aarch64'
    assert record['manual_trials_passed'] is True
    return record


identity()
if a.operation == 'guard':
    print('TZX_DRAM_GPU_HARDWARE_GUARD_PASS', json.dumps(guard()), flush=True)
elif a.operation in ('display-start', 'display-stop'):
    script = '/usr/local/lib/tzx-accel-display/tzx-display-runtime'
    if a.operation == 'display-start' and MARKER.exists():
        qualified()
        guard()
        script = str(ROOT/'display-runtime')
    run('/bin/sh', script, 'start' if a.operation == 'display-start' else 'stop')
elif a.operation == 'gpu-start':
    qualified()
    state = guard()
    if PENDING.exists():
        assert json.loads(PENDING.read_text())['boot_id'] == BOOT, 'Previous GPU boot health did not complete'
    atomic(PENDING, dict(state, health='pending'))
    assert not Path('/sys/module/panfrost').exists()
    run('modprobe', 'gpu_sched')
    run('insmod', str(ROOT/'panfrost.ko'), 'tzx_dma32=1')
    run('modprobe', 'tzx_gpu_nodes')
    assert Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() == 'Y'
    assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip() == 'auto'
    run('python3', '/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py',
        '--node', '/dev/dri/by-path/platform-tzx-de-scanout-card', timeout=18)
    print('TZX_DRAM_GPU_INITIAL_MMU_DMA32_AND_PIXEL_READY', json.dumps(state), flush=True)
elif a.operation == 'lightdm':
    command = ['/usr/sbin/lightdm']
    if MARKER.exists() and Path('/sys/module/panfrost/parameters/tzx_dma32').exists():
        qualified()
        if subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-gpu.service']).returncode == 0:
            command += ['--config=/usr/local/lib/tzx-accel-gpu/lightdm.conf']
    os.execv(command[0], command)
elif a.operation == 'health':
    qualified()
    state = guard()
    assert json.loads(PENDING.read_text())['boot_id'] == BOOT
    env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')
    for attempt in range(25):
        result = subprocess.run(['glxinfo', '-B'], env=env, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and 'Mali-G57' in result.stdout and 'Accelerated: yes' in result.stdout:
            print(result.stdout, flush=True)
            break
        time.sleep(1)
    else:
        raise RuntimeError('Accelerated desktop did not become ready')
    run('python3', '/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py',
        '--node', '/dev/dri/by-path/platform-tzx-de-scanout-card', timeout=18)
    from tzx_direct_io import read_direct
    for name in ('/usr/lib/aarch64-linux-gnu/libc.so.6', '/usr/lib/aarch64-linux-gnu/libgio-2.0.so.0.8400.4'):
        data = Path(name).read_bytes()
        assert hashlib.sha256(read_direct(Path(name))).digest() == hashlib.sha256(data).digest()
    faults = [line for line in subprocess.check_output(['dmesg'], text=True).splitlines()
              if 'panfrost' in line and any(word in line for word in ('fault', 'timeout'))]
    assert not faults, faults
    state['temperatures_mC'] = {p.joinpath('type').read_text().strip(): int(p.joinpath('temp').read_text())
                               for p in Path('/sys/class/thermal').glob('thermal_zone*')}
    physical = {'gpu-thermal', 'cpu-big-thermal', 'cpu-little-thermal', 'npu-thermal', 'ddr-thermal'}
    observed = set(state['temperatures_mC'])
    assert physical <= observed <= physical | {'tzx-board-thermal'}
    assert all(0 < v < 75000 for v in state['temperatures_mC'].values())
    atomic(Path('/var/lib/tzx/dram-gpu-boot-health.json'), dict(state, gpu_desktop='Mali-G57', status='PASS'))
    PENDING.unlink()
    syncdir(PENDING.parent)
    print('TZX_DRAM_GPU_ACCELERATED_BOOT_HEALTH_PASS', json.dumps(state), flush=True)
elif a.operation == 'fallback':
    if MARKER.exists():
        atomic(Path('/var/lib/tzx/dram-gpu-revoked.json'),
               {'boot_id': BOOT, 'reason': 'GPU startup or health failure', 'previous': json.loads(MARKER.read_text())})
        MARKER.unlink()
        syncdir(MARKER.parent)
    if PENDING.exists():
        PENDING.unlink()
        syncdir(PENDING.parent)
    run('systemctl', 'stop', 'lightdm')
    run('systemctl', 'stop', 'tzx-gpu.service')
    if Path('/sys/module/panfrost').exists():
        run('modprobe', '-r', 'panfrost')
    run('systemctl', 'restart', 'tzx-display.service')
    run('systemctl', 'start', 'lightdm')
    print('TZX_DRAM_GPU_REVOKED_SOFTWARE_DESKTOP_RESTORED', flush=True)
