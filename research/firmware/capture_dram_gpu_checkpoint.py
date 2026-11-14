"""Capture the actual verified additions and paired boot rollback, without rootfs."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('--with-cooling', action='store_true')
parser.add_argument('--name', choices=('dram-gpu-cooling-v2-installed-checkpoint',
                                     'screen-power-audio-installed-checkpoint',
                                     'screen-vblank-installed-checkpoint',
                                     'screen-doublebuffer-installed-checkpoint',
                                     'screen-standby-installed-checkpoint',
                                     'screen-poweron-installed-checkpoint'))
args = parser.parse_args()
NAME = args.name or ('dram-gpu-cooling-installed-checkpoint' if args.with_cooling else 'dram-gpu-installed-checkpoint')
assert not args.name or args.with_cooling
with_poweron = NAME == 'screen-poweron-installed-checkpoint'
with_standby = NAME == 'screen-standby-installed-checkpoint' or with_poweron
with_screen = NAME in ('screen-power-audio-installed-checkpoint', 'screen-vblank-installed-checkpoint',
                      'screen-doublebuffer-installed-checkpoint', 'screen-standby-installed-checkpoint',
                      'screen-poweron-installed-checkpoint')
with_doublebuffer = NAME == 'screen-doublebuffer-installed-checkpoint' or with_standby
with_vblank = NAME == 'screen-vblank-installed-checkpoint' or with_doublebuffer

assert os.geteuid() == 0
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
CID = Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()
assert CID == '3e01ff55454d20202010209170281b59'
ROOT = Path('/var/lib/tzx')
state = json.loads((ROOT/'dram-gpu-runtime-installed.json').read_text())
assert state['state'] == 'accelerated_autostart_cpufreq_and_controlled_recovery_verified'
baseline_boot = state['verified_boot_id']
assert json.loads((ROOT/'dram-gpu-coexistence-final.json').read_text())['boot_id'] == baseline_boot
cpu = json.loads((ROOT/'cpufreq-runtime-installed.json').read_text())
assert cpu['coexistence_verified_boot_id'] == baseline_boot and cpu['gpu_enabled'] is True
installed = dict(state['files'], **cpu['files'])
if args.with_cooling:
    cooling = json.loads((ROOT/'cpu-cooling-installed.json').read_text())
    assert cooling['state'] == 'lowered_trips_coexistence_and_actual_autostart_verified'
    assert cooling['verified_boot_id'] == BOOT and cooling['unit_enabled'] is True
    if args.name:
        assert cooling['hot_start_guard_revision'] == 2
    health = json.loads((ROOT/'dram-gpu-boot-health.json').read_text())
    assert health['boot_id'] == BOOT and health['status'] == 'PASS'
    assert not (ROOT/'dram-gpu-boot-pending.json').exists()
    check = subprocess.check_output(['python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify'], text=True)
    assert 'TZX_CPU_COOLING_PRODUCTION_ZONE_AND_QOS_PASS' in check
    assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
    for service in ('tzx-display', 'tzx-touch', 'tzx-wifi', 'tzx-bluetooth', 'tzx-audio',
                    'tzx-battery', 'tzx-thermal', 'tzx-gpu', 'tzx-cpufreq', 'tzx-rtc-log',
                    'tzx-cpu-cooling', 'tzx-dram-gpu-health', 'tzx-tablet-keys', 'lightdm'):
        assert subprocess.check_output(['systemctl', 'is-active', service+'.service'], text=True).strip() == 'active'
    pmic = json.loads((ROOT/'pmic-poweroff-installed.json').read_text())
    if with_screen:
        assert pmic['state'] == 'qualified_normal_poweroff_enabled'
        assert pmic['poweroff_tested'] is True and pmic['unit_enabled'] is True
        assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() in ('1', 'Y')
        assert subprocess.check_output(['systemctl', 'is-enabled', 'tzx-pmic-poweroff'], text=True).strip() == 'enabled'
    else:
        assert pmic['state'] == 'staged_manual_poweroff_pending' and pmic['unit_enabled'] is False
        assert not Path('/sys/module/tzx_pmic_poweroff').exists()
    for extra in (cooling['files'], pmic['files']):
        for name, digest in extra.items():
            assert name not in installed or installed[name] == digest, name
            installed[name] = digest
    if with_screen:
        audio = json.loads((ROOT/'codec-rates-installed.json').read_text())
        assert audio['state'] == 'manual_matrix_and_actual_autostart_verified'
        assert audio['verified_boot_id'] == BOOT
        screen = json.loads((ROOT/'screen-installed.json').read_text())
        assert screen['state'] == 'manual_display_and_actual_autostart_verified'
        assert screen['verified_boot_id'] == BOOT
        assert json.loads((ROOT/'screen-boot-health.json').read_text())['boot_id'] == BOOT
        assert not (ROOT/'screen-boot-pending.json').exists()
        for extra in (audio['files'], {name: item['sha256'] for name, item in screen['files'].items()}):
            for name, digest in extra.items():
                assert name not in installed or installed[name] == digest, name
                installed[name] = digest
else:
    assert baseline_boot == BOOT
contents = {}
for name, digest in installed.items():
    path = Path('/')/name
    assert path.is_file() and not path.is_symlink()
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, name
    contents[name] = data
paths = [
    '/usr/local/lib/tzx-rtc-context/runtime.py', '/usr/local/lib/tzx-rtc-context/tzx_rtc_log.ko',
    '/usr/local/lib/tzx-rtc-context/rtc_context_codec.py',
    '/etc/systemd/system/tzx-rtc-log.service.d/97-abort-context.conf',
    '/root/tzx-recovery/dram-boot-voltage/original.toc0',
    '/root/tzx-recovery/dram-boot-voltage/rtc-context-runtime.py',
    '/root/tzx-recovery/dram-boot-voltage/installer.py',
    '/root/tzx-recovery/dram-gpu-runtime/before.json',
    '/root/tzx-recovery/dram-gpu-runtime/installed-files.json',
    '/root/tzx-recovery/dram-gpu-runtime/installer.py',
    '/root/tzx-recovery/dram-gpu-runtime/runtime-package.tar.gz',
    '/root/tzx-recovery/dram-gpu-fallback-test/qualification.json',
    '/root/tzx-recovery/dram-gpu-fallback-test/intent.json',
    '/root/tzx-recovery/dram-gpu-fallback-test/fallback-result.json',
    '/home/debian/installed-bundle.json', '/boot/config-7.3.3-tzx-a523-accel1',
    '/home/debian/verify_dram_gpu_cpufreq.py', '/home/debian/verify_dram_gpu_boot_recovery.py',
]
paths += [str(ROOT/name) for name in ('gpu-qualified', 'dram-gpu-boot-health.json',
          'dram-gpu-coexistence-final.json', 'dram-gpu-cpufreq-coexistence.json',
          'dram-gpu-runtime-installed.json', 'dram-boot-first-pass.json',
          'dram-boot-voltage.json', 'cpufreq-runtime-installed.json')]
if args.with_cooling:
    paths += [str(ROOT/name) for name in ('cpu-cooling-installed.json', 'cpu-cooling-trial.json',
                                        'pmic-poweroff-installed.json')]
    for folder in ('cpu-cooling', 'pmic-poweroff'):
        backup = Path('/root/tzx-recovery')/folder
        paths += [str(backup/name) for name in ('before.json', 'files.json', 'installer.py', 'runtime-package.tar.gz')]
    cooling_backup = Path('/root/tzx-recovery/cpu-cooling')
    paths += [str(path) for folder in ('files', 'bookkeeping-before')
              for path in (cooling_backup/folder).rglob('*') if path.is_file()]
    paths += ['/home/debian/verify_cpu_cooling_trial.py', '/home/debian/verify_cpu_cooling_gpu.py',
              '/home/debian/install_cpu_cooling.py', '/home/debian/install_pmic_poweroff.py']
    if args.name:
        paths += [str(path) for path in Path('/root/tzx-recovery/cpu-cooling-hot-start-v2').rglob('*')
                  if path.is_file()]
if with_screen:
    paths += [str(path) for folder in ('screen-functions-v1', 'screen-brightness-save-v2', 'codec-rates')
              for path in (Path('/root/tzx-recovery')/folder).rglob('*') if path.is_file()]
    paths += [str(ROOT/name) for name in ('screen-installed.json', 'screen-qualified.json',
              'screen-boot-health.json', 'screen-controls-test.json', 'screen-rotation-test.json',
              'screen-reboot-intent.json', 'codec-rates-installed.json', 'codec-rates-manual.json')]
    paths += ['/home/debian/install_screen_complete.py', '/home/debian/configure_screen_desktop.py',
              '/home/debian/verify_screen_controls.py', '/home/debian/verify_screen_rotation.py',
              '/home/debian/reboot_screen_validation.py', '/home/debian/install_codec_rates.py',
              '/home/debian/upgrade_screen_brightness_save.py', '/home/debian/verify_screen_boot.py',
              '/home/debian/verify_installed_codec_rates.py', '/home/debian/verify_codec_rates.py',
              '/home/debian/.config/tzx-screen.json',
              '/home/debian/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml']
    paths += [str(path) for path in Path('/var/lib/systemd/backlight').glob('*tzx-panel*') if path.is_file()]
if with_vblank:
    assert screen['profile'] == ('screen-functions-5-poweron' if with_poweron else
                                 'screen-functions-4-standby' if with_standby else
                                 'screen-functions-3-doublebuffer' if with_doublebuffer else 'screen-functions-2-vblank')
    assert screen['persistence_verified_boot_id'] == BOOT
    proof = json.loads((ROOT/'screen-vblank-test.json').read_text())
    assert proof['boot_id'] == BOOT and proof['result'] == 'PASS'
    paths += [str(path) for path in Path('/root/tzx-recovery/screen-hardware-vblank').rglob('*') if path.is_file()]
    paths += [str(ROOT/name) for name in ('screen-vblank-test.json', 'screen-pageflip-test.json',
                                        'dsi-frame-irq-probe.json', 'screen-frame-irq-probe.json')]
    paths += ['/home/debian/upgrade_screen_vblank.py', '/home/debian/verify_screen_vblank.py',
              '/home/debian/verify_screen_pageflip.py']
if with_doublebuffer:
    assert int(Path('/sys/module/tzx_display/parameters/screen_buffer_errors').read_text()) == 0
    assert screen['settings_save_revision'] == 2
    for name in ('screen-doublebuffer-test.json', 'screen-pageflip-test.json'):
        proof = json.loads((ROOT/name).read_text())
        assert proof['boot_id'] == BOOT and proof['result'] == 'PASS', name
    paths += [str(path) for folder in ('screen-doublebuffer-r2', 'screen-settings-save-v2')
              for path in (Path('/root/tzx-recovery')/folder).rglob('*') if path.is_file()]
    paths += [str(ROOT/'screen-doublebuffer-test.json'), '/home/debian/upgrade_screen_doublebuffer.py',
              '/home/debian/verify_screen_doublebuffer.py', str(ROOT/'screen-settings-concurrency.json'),
              '/home/debian/upgrade_screen_settings.py', '/home/debian/verify_screen_settings_concurrency.py']
if with_standby:
    assert int(Path('/sys/module/tzx_display/parameters/screen_panel_errors').read_text()) == 0
    assert Path('/sys/module/tzx_display/parameters/screen_panel_sleeping').read_text().strip() == 'N'
    proof = json.loads((ROOT/'screen-standby-test.json').read_text())
    assert proof['boot_id'] == BOOT and proof['result'] == 'PASS'
    paths += [str(path) for path in Path('/root/tzx-recovery/screen-standby').rglob('*') if path.is_file()]
    paths += [str(ROOT/'screen-standby-test.json'), '/home/debian/upgrade_screen_standby.py',
              '/home/debian/verify_screen_standby.py']
if with_poweron:
    proof = json.loads((ROOT/'screen-poweron-test.json').read_text())
    assert proof['boot_id'] == BOOT and proof['result'] == 'PASS'
    assert proof['kernel_console_rotation_enabled'] is True and proof['fbcon_rotate'] == '1'
    kernel = json.loads((ROOT/'screen-boot-kernel-installed.json').read_text())
    assert kernel['state'] == 'actual_boot_verified' and kernel['verified_boot_id'] == BOOT
    paths += [str(path) for folder in ('screen-poweron', 'screen-boot-kernel')
              for path in (Path('/root/tzx-recovery')/folder).rglob('*') if path.is_file()]
    paths += [str(ROOT/name) for name in ('screen-poweron-test.json', 'screen-display-setup.json',
                                        'screen-boot-kernel-installed.json')]
    paths += ['/home/debian/upgrade_screen_poweron.py', '/home/debian/install_screen_boot_kernel.py',
              '/home/debian/verify_screen_poweron.py', '/boot/Image', '/boot/board.dtb',
              '/boot/initramfs.cpio.gz', '/boot/kernel.config']
assert len(paths) == len(set(paths))
for name in paths:
    path = Path(name)
    assert path.is_file() and not path.is_symlink(), name
    contents[name.lstrip('/')] = path.read_bytes()
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    contents['raw/current-toc0-lba256.bin'] = os.pread(fd, 40960, 256*512)
    contents['raw/active-header-lba4096.bin'] = os.pread(fd, 512, 4096*512)
    contents['raw/k5-bundle-lba65536.bin'] = os.pread(fd, 14876672, 65536*512)
    contents['raw/gpt-front-128-sectors-read-only.bin'] = os.pread(fd, 65536, 0)
    contents['raw/gpt-back-128-sectors-read-only.bin'] = os.pread(fd, 65536, (244318208-128)*512)
    if with_poweron:
        contents['raw/screen-boot-bundle-lba98304.bin'] = os.pread(fd, 14942208, 98304*512)
finally:
    os.close(fd)
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(contents['raw/current-toc0-lba256.bin']) == '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
assert sha(contents['raw/k5-bundle-lba65536.bin']) == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
if with_poweron:
    assert sha(contents['raw/screen-boot-bundle-lba98304.bin']) == 'f6b644da1a8276b599c9e3f6b7944c6eb246ddd8c8adf0cbe5ba20116c6a3829'
    assert contents['raw/active-header-lba4096.bin'] == contents['raw/screen-boot-bundle-lba98304.bin'][:512]
else:
    assert contents['raw/active-header-lba4096.bin'] == contents['raw/k5-bundle-lba65536.bin'][:512]
assert sha(contents['root/tzx-recovery/dram-boot-voltage/original.toc0']) == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
assert sha(contents['usr/local/lib/tzx-rtc-context/runtime.py']) == 'e1f7beb91db90ac8443dc46fff846754f4d34d7ca6d6dc63f8e5c481e39e2f44'
audit_unit = ('tzx-screen-final-files.service' if with_screen else
              'tzx-cpu-cooling-boot-files.service' if args.with_cooling else 'tzx-dram-gpu-final-files.service')
props = subprocess.check_output(['systemctl', 'show', audit_unit, '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus'], text=True)
assert all(value in props for value in ('ActiveState=inactive', 'Result=success', 'ExecMainStatus=0'))
audit = subprocess.check_output(['journalctl', '-b', '-u', audit_unit, '-o', 'cat', '--no-pager'], text=True)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
contents['proof/final-boot-file-audit.txt'] = audit.encode()
if args.with_cooling:
    contents['proof/current-cooling-health.txt'] = check.encode()
    for unit in ('tzx-cpu-cooling', 'tzx-dram-gpu-health'):
        contents['proof/current-boot-'+unit+'.txt'] = subprocess.check_output(
            ['journalctl', '-b', '-u', unit+'.service', '-o', 'short-iso', '--no-pager'])
if with_screen:
    for unit in ('tzx-screen-health', 'tzx-pmic-poweroff', 'systemd-backlight@backlight:tzx-panel'):
        contents['proof/current-boot-'+unit.replace(':', '-')+'.txt'] = subprocess.check_output(
            ['journalctl', '-b', '-u', unit+'.service', '-o', 'short-iso', '--no-pager'])
manifest = {'cid': CID, 'boot_id': BOOT, 'kernel': os.uname().version,
            'scope': 'actual installed trained-DRAM/GPU/CPUfreq additions, optional cooling and staged untested poweroff, #5 bundle, rollback pair; no rootfs or credentials',
            'GPT_must_not_be_written_at_LBA16': True, 'hardware_qualification': 'bounded tests',
            'cooling_included': args.with_cooling, 'base_gpu_qualification_boot_id': baseline_boot,
            'poweroff_cold_boot_tested': with_screen,
            'screen_functions_included': with_screen,
            'restore_order': (['python3 /home/debian/configure_screen_desktop.py restore',
                              'python3 /home/debian/install_screen_complete.py restore',
                              'python3 /home/debian/install_codec_rates.py restore'] if with_screen else []) +
                (['python3 /home/debian/install_cpu_cooling.py restore'] if args.with_cooling else []) + [
                'python3 /home/debian/install_dram_gpu_runtime.py --restore',
                'stop and disable tzx-cpufreq.service',
                'python3 /home/debian/install_dram_boot_voltage.py --restore'],
            'files': {name: sha(data) for name, data in contents.items()}}
if with_screen:
    manifest['scope'] = 'actual verified screen functions, poweroff/coldboot, codec rates, trained DRAM/GPU/CPU/cooling, #5 boot and rollback files; no rootfs or credentials'
    manifest['screen_low_level_limitations'] = ['fixed single-buffer shadow scanout', 'no DRM hardware vblank yet',
                                               'GPIO/PWM and panel rail use guarded board-specific ownership']
if with_vblank:
    manifest['hardware_DRM_vblank'] = 'DSI1 VIDEO_VBLK, real WAIT_VBLANK and page-flip events'
    manifest['screen_low_level_limitations'] = ['fixed single-buffer shadow scanout can still tear',
                                               'GPIO/PWM and panel rail use guarded board-specific ownership',
                                               'DPMS turns off backlight; full panel power gating not qualified']
    manifest['restore_screen_v1_only'] = 'python3 /home/debian/upgrade_screen_vblank.py restore'
if with_doublebuffer:
    manifest['hardware_scanout'] = 'two independent DMA32 buffers, RCQ FINISH and address readback before reuse'
    manifest['screen_low_level_limitations'] = ['CPU copy into permanent scanout buffers; no zero-copy scanout',
                                               'GPIO/PWM and panel rail use guarded board-specific ownership',
                                               'DPMS turns off backlight; full panel power gating not qualified']
    manifest['restore_screen_v2_only'] = 'python3 /home/debian/upgrade_screen_doublebuffer.py restore'
if with_standby:
    manifest['panel_DPMS'] = 'standard DCS sleep/wake, DSI video stopped; five cycles and actual boot qualified'
    manifest['screen_low_level_limitations'] = ['CPU copy into permanent scanout buffers; no zero-copy scanout',
                                               'GPIO/PWM and panel rail use guarded board-specific ownership',
                                               'bias/supply stay powered in DPMS; full rail gating and system suspend not qualified']
    manifest['restore_screen_v3_only'] = 'python3 /home/debian/upgrade_screen_standby.py restore'
if with_poweron:
    manifest['screen_poweron'] = 'PD23 held low before bias/reset; PWM only after successful first-frame RCQ'
    manifest['screen_default'] = 'right landscape in fbcon, initial Xorg, before greeter and each desktop session'
    manifest['kernel_change'] = 'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y; all existing exported symbol CRCs unchanged'
    manifest['restore_screen_v4_only'] = 'python3 /home/debian/upgrade_screen_poweron.py restore'
    manifest['restore_original_kernel'] = 'python3 /home/debian/install_screen_boot_kernel.py restore; then reboot'
    manifest['previous_pmic_poweroff_key_on_tested'] = manifest.pop('poweroff_cold_boot_tested')
    manifest['this_screen_revision_poweroff_key_on_tested'] = False
    manifest['this_screen_revision_poweroff_key_on_status'] = 'deferred at user request; keep desktop running'
contents['MANIFEST.json'] = json.dumps(manifest, indent=2).encode()+b'\n'
target = Path('/home/debian')/(NAME+'.tar.gz')
with target.open('xb') as stream:
    with tarfile.open(fileobj=stream, mode='w:gz', compresslevel=3) as archive:
        for name, data in sorted(contents.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(data), 0o600
            archive.addfile(item, io.BytesIO(data))
    stream.flush()
    os.fsync(stream.fileno())
target.chmod(0o644)
directory = os.open(target.parent, os.O_DIRECTORY)
os.fsync(directory)
os.close(directory)
print('DRAM_GPU_INSTALLED_CHECKPOINT_CREATED', json.dumps({'path': str(target),
      'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size,
      'files': len(manifest['files']), 'boot_id': BOOT}), flush=True)
