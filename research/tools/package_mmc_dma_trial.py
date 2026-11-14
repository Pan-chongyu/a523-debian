"""Pin the MMC-only kernel, spare-slot transaction, and identical v8 trial."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / 'build/mmc-dma-kernel'
build = json.loads((folder / 'BUILD_COMPLETE.json').read_text())
assert build['kernel_build'] == 8 and build['configuration_unchanged']
assert build['external_modules_ABI_unchanged'] and not build['changed_symbol_crcs']
compose = (root / 'tools/compose_va48_bundle.py').read_text()
compose = compose.replace("folder=root/'build/va48-kernel'", "folder=root/'build/mmc-dma-kernel'")
compose = compose.replace("'7.3.3-tzx-a523-va48' and build['kernel_build']==7", "'7.3.3-tzx-a523-accel1' and build['kernel_build']==8")
compose = compose.replace('48bit VA/PA translation comparison', 'MMC mapped scatterlist and 34-bit DMA-mask comparison')
compose = compose.replace('VA48_BUNDLE_COMPOSED', 'MMC_DMA_BUNDLE_COMPOSED')
assert "folder=root/'build/mmc-dma-kernel'" in compose
exec(compile(compose, str(root/'tools/compose_va48_bundle.py'), 'exec'))
manifest = json.loads((folder / 'linux-bundle.json').read_text())

source = (root / 'firmware/install_pagecheck_kernel.py').read_text()
source = source.replace('pagecheck', 'mmc-dma').replace('PAGECHECK', 'MMC_DMA')
replacements = {
    "('#5 ', '#6 '))": "('#5 ', '#8 '))",
    '606a18d4eeeee98ccdff67fca33911437380e79b970a504f2356ba99dec37116': manifest['sha256'],
    '8eb3abbbfc1ad05214d65cd63ac7ec145398782c3e858d20095d5f24ae660972': build['files']['kernel.config'],
    '98304, 15020032': '98304, ' + str(manifest['bytes']),
    'd741bbc184836bfc08cbbf6667f056d6a5b826f0c84c12b301b0cbfede9215c9': build['files']['Image'],
    'diagnostic_6_reboot_pending': 'diagnostic_8_reboot_pending',
    'diagnostic_6_slot_lba': 'diagnostic_8_slot_lba',
    '#6 diagnostic': '#8 diagnostic',
}
for before, after in replacements.items():
    assert before in source, before
    source = source.replace(before, after)
needle = '        os.sync()\n        assert os.pwrite(fd, candidate, NEW_LBA*512) == len(candidate)'
assert source.count(needle) == 1
source = source.replace(needle,
    "        prior_spare = os.pread(fd, 14876672, NEW_LBA*512)\n"
    "        assert sha(prior_spare) in ('0d9c3e238b5910f299c24d9c09d2a759e06076756150f5560a0f8af3148da985', NEW_SHA)\n"
    "        os.sync()\n        assert os.pwrite(fd, candidate, NEW_LBA*512) == len(candidate)")
assert '#6 ' not in source and 'pagecheck' not in source
compile(source, 'install_mmc_dma_kernel.py', 'exec')
installer = root/'firmware/install_mmc_dma_kernel.py'
assert not installer.exists()
installer.write_text(source, encoding='utf8', newline='\n')

trial = (root/'firmware/run_guarded_copy_trial.py').read_text()
trial = trial.replace("and '#5 ' in os.uname().version", "and '#8 ' in os.uname().version")
trial = trial.replace('3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c', manifest['sha256'])
trial = trial.replace('copy-readonly-v8-high', 'copy-mmc-dma-v8-high')
trial = trial.replace('GUARDED_COPY_TRIAL', 'MMC_DMA_GUARDED_COPY_TRIAL')
compile(trial, 'run_mmc_dma_copy_trial.py', 'exec')
target = root/'firmware/run_mmc_dma_copy_trial.py'
assert not target.exists()
target.write_text(trial, encoding='utf8', newline='\n')
record = {'kernel_build': 8, 'full_ram_retained': True, 'voltage_unchanged': True,
          'original_slot_retained': 65536, 'candidate_slot': 98304,
          'bundle_sha256': manifest['sha256'], 'bundle_bytes': manifest['bytes'],
          'installer_sha256': hashlib.sha256(installer.read_bytes()).hexdigest(),
          'trial_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'hardware_boot_verified': False}
(folder/'TRIAL_PACKAGE.json').write_text(json.dumps(record, indent=2)+'\n')
print('MMC_DMA_TRIAL_PACKAGE_READY', json.dumps(record))
