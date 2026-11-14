"""Load diagnostic modules under /run overrides; reboot always restores baseline."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import subprocess
import struct

parser = argparse.ArgumentParser()
parser.add_argument('--trial-id', default='2')
parser.add_argument('--keep-awake', action='store_true')
parser.add_argument('--mmu-init', action='store_true')
parser.add_argument('--aarch64-pgtable', action='store_true')
parser.add_argument('--restart-desktop-on-exit', action='store_true')
args = parser.parse_args()
assert args.trial_id and all(c.isalnum() or c == '-' for c in args.trial_id)

assert os.geteuid() == 0 and any(build in os.uname().version for build in ('#4 ', '#5 ', '#6 '))
if '#6 ' in os.uname().version:
    assert hashlib.sha256(Path('/boot/config-7.3.3-tzx-a523-accel1').read_bytes()).hexdigest() == '8eb3abbbfc1ad05214d65cd63ac7ec145398782c3e858d20095d5f24ae660972'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert not Path('/sys/module/panfrost').exists()
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert int(next(row.split()[1] for row in Path('/proc/meminfo').read_text().splitlines()
                if row.startswith('MemTotal:'))) > 3900000
shas = {'panfrost-dma32.ko':'95268f13a0c01d3b95e62076a895a5f6261bb930f84aa8a66024e7ca70fe5df1',
        'tzx_display-dma32.ko':'49faef93a64f7c4c24dcf330fa8d21c47f9681a848e83bd6716bbfa4643b4440'}
panfrost_module = 'panfrost-dma32.ko'
if args.mmu_init:
    del shas[panfrost_module]
    panfrost_module = 'panfrost-dma32-mmu-init.ko'
    shas[panfrost_module] = '41cf7162f1322cd1936e318f8f8c6feaf0ee39d9d17025571e697dd61d9fd080'
if args.aarch64_pgtable:
    assert args.mmu_init
    del shas[panfrost_module]
    panfrost_module = 'panfrost-dma32-aarch64.ko'
    shas[panfrost_module] = 'ad4127adbd990361f89dfa65e3707927609f7eefedc766cd03dedb25f6ba97ae'
for name,digest in shas.items():
    assert hashlib.sha256(Path('/home/debian',name).read_bytes()).hexdigest() == digest
original = Path('/usr/local/lib/tzx-accel-display/tzx-display-runtime').read_text()
assert original.count('    modprobe tzx_display\n') == 1
replacement = '''    for tzx_dep in $(modinfo -F depends /home/debian/tzx_display-dma32.ko | tr ',' ' '); do
        modprobe "$tzx_dep"
    done
    insmod /home/debian/tzx_display-dma32.ko
'''
runtime = Path('/run/tzx-dma32-display-runtime')
runtime.write_text(original.replace('    modprobe tzx_display\n',replacement))
runtime.chmod(0o700)
dropin = Path('/run/systemd/system/tzx-display.service.d/98-dma32-test.conf')
dropin.parent.mkdir(parents=True,exist_ok=True)
dropin.write_text('[Service]\nExecStart=\nExecStart=/bin/sh /run/tzx-dma32-display-runtime start\n')
rollback=Path('/run/tzx-dma32-rollback.py')
rollback.write_text(Path(__file__).with_name('cleanup_gpu_dma32_trial.py').read_text())
rollback.chmod(0o700)
rollback_command = ['/usr/bin/python3', str(rollback)]
if args.restart_desktop_on_exit:
    rollback_command.append('--restart-desktop')
def run(*args):
    subprocess.run(args,check=True,timeout=45,
                   env=dict(os.environ, MESA_SHADER_CACHE_DISABLE='true'))
if subprocess.run(['systemctl','is-active','--quiet',
                   'tzx-dma32-independent-rollback.timer']).returncode == 0:
    run('systemctl','stop','tzx-dma32-independent-rollback.timer')
run('systemd-run','--unit=tzx-dma32-independent-rollback'+args.trial_id,'--on-active=14min',
    *rollback_command)
try:
    run('systemctl','stop','lightdm')
    run('systemctl','stop','tzx-display')
    assert not Path('/sys/module/tzx_display').exists()
    run('systemctl','daemon-reload')
    run('systemctl','start','tzx-display')
    run('systemctl','start','lightdm')
    run('modprobe','gpu_sched')
    run('insmod','/home/debian/'+panfrost_module,'tzx_dma32=1')
    assert Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() == 'Y'
    run('modprobe','tzx_gpu_nodes')
    assert Path('/dev/dri/renderD128').exists()
    if args.keep_awake:
        control = Path('/sys/bus/platform/devices/1800000.gpu/power/control')
        control.write_text('on\n')
        assert control.read_text().strip() == 'on'
        print('GPU_DMA32_TRIAL_RUNTIME_AUTOSUSPEND_DISABLED', flush=True)
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 0x3000, flags=mmap.MAP_SHARED,
                       prot=mmap.PROT_READ, offset=0x01800000) as registers:
            snapshot = {hex(offset): hex(struct.unpack_from('<I', registers, offset)[0])
                        for offset in (0x1008, 0x2000, 0x2008, 0x200c)}
        print('GPU_BEFORE_FIRST_JOB', json.dumps({'registers': snapshot,
              'runtime_status': Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip(),
              'initial_mmu_reset_patch': args.mmu_init,
              'aarch64_page_table_comparison': args.aarch64_pgtable}), flush=True)
    finally:
        os.close(fd)
    run('python3','/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py',
        '--node','/dev/dri/by-path/platform-tzx-de-scanout-card')
    print('GPU_DMA32_MANUAL_MODULES_AND_PIXEL_READBACK_READY_FULL_RAM',flush=True)
except BaseException:
    run(*rollback_command)
    raise
