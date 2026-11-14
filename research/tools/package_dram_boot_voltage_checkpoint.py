"""Freeze the exact installed/rollback boot pair and diagnostic evidence."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

p = argparse.ArgumentParser()
p.add_argument('--name', default='dram-boot-voltage-checkpoint')
p.add_argument('--with-cooling', action='store_true')
p.add_argument('--with-screen', action='store_true')
p.add_argument('--with-standby', action='store_true')
p.add_argument('--with-poweron', action='store_true')
a = p.parse_args()
assert a.name.startswith('dram-boot-voltage-') and all(c.isalnum() or c == '-' for c in a.name)
root = Path(__file__).resolve().parents[1]
paths = [
    'build/known-good-loader/chain-loader.bin', 'build/known-good-loader/chain-loader.toc0',
    'build/known-good-loader/chain-loader.toc0.json',
    'build/rtc-context/runtime.py', 'build/rtc-context/tzx_rtc_log.ko',
    'firmware/dram_boot_voltage_hook.c', 'firmware/install_dram_boot_voltage.py',
    'firmware/read_dram_boot_log.py', 'firmware/read_axp_dram_status.py',
    'firmware/run_dram_boot_copy_trial.py', 'firmware/run_dram_boot_gpu_trial.py',
    'firmware/finish_dram_boot_gpu_trial.py', 'firmware/install_dram_boot_gpu_unit.py',
    'firmware/tzx-dram-boot-gpu-diagnostic.service',
    'firmware/run_dram_boot_low_copy_trial.py', 'firmware/verify_dram_boot_gpu_idle.py',
    'firmware/reboot_dram_boot_validation.py', 'firmware/tzx-dram-boot-gpu-autosuspend.service',
    'firmware/tzx_dram_gpu_runtime.py', 'firmware/install_dram_gpu_runtime.py',
    'firmware/verify_dram_gpu_cpufreq.py', 'firmware/verify_dram_gpu_boot_recovery.py',
    'firmware/capture_dram_gpu_checkpoint.py', 'tools/pull_dram_gpu_checkpoint.py',
    'build/dram-gpu-installed-checkpoint.json',
    'tools/package_dram_gpu_runtime.py',
    'tools/build_dram_boot_voltage_hook.sh', 'tools/compose_dram_boot_voltage.py',
    'tools/prepare_dram_boot_runtime.py', 'tools/test_dram_boot_voltage_emulation.py',
    'tools/package_dram_boot_voltage_checkpoint.py', 'tools/flash_loader_fel.py',
    'DRAM-VOLTAGE-INTEGRATION.md', 'PROGRESS.md', 'GPU-MEMORY-DEBUG.md',
    'GPU-THERMAL-INTEGRATION.md', 'CPU-COPY-ISOLATION.md', 'CPU-POWER-BRINGUP.md',
    'RTC-ABORT-CONTEXT.md',
]
paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'build/dram-boot-voltage').iterdir()
          if f.is_file()]
paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'evidence').glob('dram-boot-voltage-*')
          if f.is_file()]
paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'evidence').glob('dram-gpu-*')
          if f.is_file()]
paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'build/dram-gpu-runtime').iterdir()
          if f.is_file()]
if a.with_cooling:
    paths += [
        'CPU-COOLING-INTEGRATION.md', 'SENSORS-CAMERA-BRINGUP.md', 'POWER-OFF-COLD-BOOT.md',
        'firmware/tzx_cpu_cooling.c', 'firmware/tzx_cpu_cooling_runtime.py',
        'firmware/tzx-cpu-cooling.service', 'firmware/install_cpu_cooling.py',
        'firmware/verify_cpu_cooling_trial.py', 'firmware/verify_cpu_cooling_gpu.py',
        'firmware/upgrade_cpu_cooling_hot_start.py', 'tools/build_cpu_cooling.sh',
        'tools/package_cpu_cooling.py', 'tools/prepare_cooling_gpu_runtime.py',
        'tools/test_cpu_cooling_hot_inspection.py',
        'tools/verify_checkpoint_usb_transfers.py',
        'firmware/tzx_candidate_i2c.c', 'firmware/probe_candidate_sensor_ids.py',
        'tools/build_candidate_i2c.sh', 'build/candidate-i2c/tzx_candidate_i2c.ko',
        'firmware/tzx_pmic_poweroff.c', 'firmware/tzx_pmic_poweroff_runtime.py',
        'firmware/tzx-pmic-poweroff.service', 'firmware/install_pmic_poweroff.py',
        'firmware/read_pmic_shutdown_status.py', 'tools/build_pmic_poweroff.sh',
        'tools/package_pmic_poweroff.py',
        'build/dram-gpu-cooling-installed-checkpoint.json',
        'build/dram-gpu-cooling-v2-installed-checkpoint.json',
    ]
    for folder in ('cpu-cooling', 'cpu-cooling-v1', 'pmic-poweroff'):
        paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'build'/folder).iterdir() if f.is_file()]
    for prefix in ('cpu-cooling-', 'candidate-sensor-', 'pmic-poweroff-', 'adaptation-current-cooling-'):
        paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'evidence').glob(prefix+'*') if f.is_file()]
if a.with_screen:
    assert a.with_cooling
    paths += ['DISPLAY-INTEGRATION.md', 'AUDIO-INTEGRATION.md',
              'tools/restart_verified_emmc_fel.py', 'tools/fel_device.py',
              'upstream/A523-root/tools/fel-emmc.bin', 'upstream/xfel/chips/a523_a527_t527.c',
              'build/screen-power-audio-installed-checkpoint.json', 'build/screen-vblank-installed-checkpoint.json',
              'build/screen-doublebuffer-installed-checkpoint.json']
    for pattern in ('*screen*', '*dsi_irq*', '*codec_rates*', '*audio_rates*'):
        paths += [str(f.relative_to(root)).replace('\\', '/') for folder in ('firmware', 'tools')
                  for f in (root/folder).glob(pattern) if f.is_file()]
    for folder in ('screen-complete', 'screen-vblank', 'screen-doublebuffer', 'screen-doublebuffer-r2', 'screen-standby',
                   'screen-irq-probe', 'dsi-irq-probe', 'audio-rates'):
        paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'build'/folder).rglob('*') if f.is_file()]
    for prefix in ('screen-', 'dsi-frame-irq-'):
        paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'evidence').glob(prefix+'*') if f.is_file()]
    paths = sorted(set(paths))
if a.with_standby:
    assert a.with_screen
    paths += ['build/screen-standby-installed-checkpoint.json']
if a.with_poweron:
    assert a.with_standby
    paths += ['build/screen-poweron-installed-checkpoint.json', 'build/screen-poweron-installed-scoped-checkpoint.json',
              'tools/scope_screen_poweron_checkpoint.py', 'firmware/install_screen_boot_kernel.py',
              'tools/build_screen_boot_kernel.sh', 'tools/compose_screen_boot_bundle.py',
              'tools/prepare_screen_poweron_package.py', 'tools/prepare_screen_poweron_installer.py']
    for folder in ('screen-poweron', 'screen-boot-kernel'):
        paths += [str(f.relative_to(root)).replace('\\', '/') for f in (root/'build'/folder).rglob('*') if f.is_file()]
    paths = sorted(set(paths))
assert len(paths) == len(set(paths))
contents = {name: (root/name).read_bytes() for name in sorted(paths)}
hashes = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
assert hashes['build/known-good-loader/chain-loader.toc0'] == 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
assert hashes['build/dram-boot-voltage/loader.toc0'] == '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
assert hashes['build/rtc-context/runtime.py'] == 'b1045903561eca454a7e9fe8158d5df29de37047ec31a2555a0dfb986a005738'
assert hashes['build/dram-boot-voltage/rtc-context-runtime.py'] == 'e1f7beb91db90ac8443dc46fff846754f4d34d7ca6d6dc63f8e5c481e39e2f44'
assert all(not any(token in name.lower() for token in ('private/', 'credentials', 'initial-login', 'id_ed25519'))
           for name in contents)
manifest = {'cid': '3e01ff55454d20202010209170281b59', 'boot_partition_lba': 256,
            'toc0_bytes': 40960, 'full_4GiB': True, 'qualification': 'bounded_hardware_trials',
            'kernel_bundle_unchanged_sha256': '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c',
            'restore_order': (['firmware/configure_screen_desktop.py restore',
                               'firmware/install_screen_complete.py restore',
                               'firmware/install_codec_rates.py restore'] if a.with_screen else []) +
                (['firmware/install_cpu_cooling.py restore'] if a.with_cooling else []) + [
                              'firmware/install_dram_gpu_runtime.py --restore',
                              'stop and disable tzx-cpufreq.service',
                              'firmware/install_dram_boot_voltage.py --restore'],
            'run_time_voltage_adjustment': False, 'files': hashes}
destination = root/'build'/(a.name+'.tar.gz')
if a.with_poweron:
    manifest['original_kernel_bundle_sha256'] = manifest.pop('kernel_bundle_unchanged_sha256')
    manifest['active_kernel_bundle_sha256'] = 'f6b644da1a8276b599c9e3f6b7944c6eb246ddd8c8adf0cbe5ba20116c6a3829'
    manifest['active_kernel_storage_lba'] = 98304
    manifest['screen_default_orientation'] = 'right'
    manifest['actual_installed_checkpoint'] = 'screen-poweron-installed-scoped-checkpoint.tar.gz'
    manifest['actual_installed_checkpoint_sha256'] = '618213cdbc7b0f22988b0b705f111a0d4a1887bfc3452c1ee2afa10ea28a3bc8'
    manifest['this_screen_revision_poweroff_key_on_tested'] = False
    manifest['restore_screen_v4_only'] = 'firmware/upgrade_screen_poweron.py restore'
    manifest['restore_original_kernel'] = 'firmware/install_screen_boot_kernel.py restore; then reboot'
assert not destination.exists()
with tarfile.open(destination, 'w:gz') as archive:
    for name, data in dict(contents, **{'MANIFEST.json': json.dumps(manifest, indent=2).encode()+b'\n'}).items():
        item = tarfile.TarInfo(name)
        item.size = len(data)
        item.mode = 0o600
        archive.addfile(item, io.BytesIO(data))
with tarfile.open(destination, 'r:gz') as archive:
    assert {f.name for f in archive.getmembers()} == set(contents) | {'MANIFEST.json'}
    for name, digest in hashes.items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest, name
record = dict(manifest, archive_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
              archive_bytes=destination.stat().st_size, every_member_verified=True)
destination.with_suffix('.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8')
print('DRAM_BOOT_VOLTAGE_CHECKPOINT_EVERY_MEMBER_VERIFIED', json.dumps({
    'path': str(destination), 'files': len(contents), 'bytes': record['archive_bytes'],
    'sha256': record['archive_sha256']}))
