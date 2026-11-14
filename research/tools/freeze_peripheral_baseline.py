"""Freeze the boot-tested periph1 desktop without enabling experimental audio."""
import hashlib
import json
import struct
import tarfile
import zlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'build/peripheral-kernel'
destination = root / 'build/periph1-desktop-verified'
expected_bundle = 'a4821c0a38f1aa00fdd45b5678221c325f839c3bcd8eeb2c57e9b01a2f129aaa'
expected_loader = 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_package(path, metadata_name, digest_name):
    data = path.read_bytes()
    metadata = json.loads((path.parent / metadata_name).read_text())
    assert sha(data) == metadata[digest_name], path
    with tarfile.open(path, 'r:gz') as archive:
        names = archive.getnames()
        assert len(names) == len(set(names))
        manifest = json.load(archive.extractfile('FILES.json'))
        assert manifest == metadata['files']
        for name, digest in manifest.items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha(archive.extractfile(name).read()) == digest, name
        compile(archive.extractfile('install.py').read(), str(path / 'install.py'), 'exec')
    return len(manifest)


manifest = json.loads((source / 'linux-bundle.json').read_text())
bundle = (source / 'linux-bundle.bin').read_bytes()
assert sha(bundle) == manifest['sha256'] == expected_bundle
assert len(bundle) == manifest['bytes'] == manifest['sectors'] * 512
assert manifest['start_lba'] == 4096
assert bundle[:8] == b'A523BND1'
assert struct.unpack_from('<II', bundle, 8) == (1, 5)
header = bytearray(bundle[:512])
header_crc = struct.unpack_from('<I', header, 16)[0]
struct.pack_into('<I', header, 16, 0)
assert zlib.crc32(header) == header_crc
payloads = {}
end = 512
for index, item in enumerate(manifest['items']):
    lba, size, address, crc, reserved1, reserved2 = struct.unpack_from('<6I', bundle, 32 + index * 24)
    assert (lba, size, address) == (item['lba'], item['bytes'], int(item['load_address'], 16))
    assert reserved1 == reserved2 == 0
    start = (lba - 4096) * 512
    rounded = (size + 511) & ~511
    assert start == end and start + rounded <= len(bundle)
    assert zlib.crc32(bundle[start:start + rounded]) == crc
    data = bundle[start:start + size]
    assert sha(data) == item['sha256']
    assert Path(item['file']).name == item['file']
    payloads['boot/' + item['file']] = data
    end = start + rounded
assert end == len(bundle)
assert 4096 + len(bundle) // 512 < 131072
assert payloads['boot/Image'] == (source / 'Image').read_bytes()
assert payloads['boot/linux-entry.bin'] == (source / 'linux-entry.bin').read_bytes()

first_boot = json.loads((root / 'evidence/peripheral-first-boot.json').read_text())
later_boot = json.loads((root / 'evidence/bluetooth-raw-init-autostart-reboot.json').read_text())
for observation in (first_boot, later_boot):
    assert observation['state'] == 'SSH_READY'
    assert '7.3.3-tzx-a523-periph1 #2' in observation['linux_identity']
readback = (root / 'evidence/peripheral-bundle-readback-reboot.txt').read_text()
assert 'UPDATED_BUNDLE_FULL_READBACK_PASS:' + expected_bundle in readback
assert sha((root / 'build/known-good-loader/chain-loader.toc0').read_bytes()) == expected_loader
package_counts = {
    'graphics-runtime': verify_package(source / 'graphics-runtime.tar.gz', 'graphics-runtime.json', 'archive_sha256'),
    'bluetooth-runtime': verify_package(source / 'bluetooth-runtime.tar.gz', 'bluetooth-runtime.json', 'archive_sha256'),
}

manifest['hardware_boot_verified'] = True
manifest['verification_evidence'] = [
    'evidence/peripheral-first-boot.json',
    'evidence/peripheral-bundle-readback-reboot.txt',
    'evidence/bluetooth-raw-init-autostart-reboot.json',
]
manifest['verified_boot_ids'] = [first_boot['linux_boot_id'], later_boot['linux_boot_id']]
(source / 'linux-bundle.json').write_text(json.dumps(manifest, indent=2) + '\n')
graphics = json.loads((source / 'graphics-runtime.json').read_text())
graphics['boot_verified'] = True
graphics['verification_evidence'] = ['evidence/peripheral-desktop-health.txt', 'evidence/desktop-periph1.png']
(source / 'graphics-runtime.json').write_text(json.dumps(graphics, indent=2) + '\n')
bluetooth = json.loads((source / 'bluetooth-runtime.json').read_text())
bluetooth['stable_address_runtime_verified'] = True
bluetooth['raw_init_autostart_reboot_verified'] = True
bluetooth['verification_evidence'] = [
    'evidence/bluetooth-first-automatic-success-codec-error.txt',
    'evidence/bluetooth-stable-address-test.txt',
]
(source / 'bluetooth-runtime.json').write_text(json.dumps(bluetooth, indent=2) + '\n')

destination.mkdir(exist_ok=False)
frozen = {}


def save(name, data):
    path = destination / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    frozen[name] = {'bytes': len(data), 'sha256': sha(data)}


for name, data in payloads.items():
    save(name, data)
for name in ('Image', 'kernel.config', 'linux-bundle.bin', 'linux-bundle.json',
             'linux-entry.bin', 'linux-entry.elf', 'linux-entry.disassembly',
             'graphics-runtime.tar.gz', 'graphics-runtime.json',
             'bluetooth-runtime.tar.gz', 'bluetooth-runtime.json', 'tzx_display.ko', 'tzx_bt_runtime.ko'):
    save('build/peripheral-kernel/' + name, (source / name).read_bytes())
for name in ('chain-loader.toc0',):
    save('build/known-good-loader/' + name, (root / 'build/known-good-loader' / name).read_bytes())
save('build/runtime-peripherals.tar.gz', (root / 'build/runtime-peripherals.tar.gz').read_bytes())
source_names = (
    'firmware/linux_entry.S', 'firmware/tzx_drm.c', 'firmware/tzx_de_scanout.c',
    'firmware/tzx_dsi_probe.c', 'firmware/tzx_dsi_phy.h', 'firmware/tzx_dsi_video.h',
    'firmware/tzx_battery.c', 'firmware/tzx_gsl3670.c', 'firmware/tzx_touch_runtime.c',
    'firmware/tzx_wifi_runtime.c', 'firmware/tzx_bt_runtime.c', 'firmware/tzx_bluetooth_runtime.py',
    'firmware/tzx-display-runtime', 'firmware/tzx-display.service',
    'firmware/tzx-bt-hardware.service', 'firmware/tzx-bluetooth.service',
    'tools/build_peripheral_kernel.sh', 'tools/build_aligned_entry.sh',
    'tools/build_drm_display.sh', 'tools/build_graphics_peripherals.sh',
    'tools/build_bt_runtime.sh', 'tools/package_graphics_runtime.py',
    'tools/package_bt_runtime.py', 'tools/make_bundle_update.py',
    'tools/ensure_usb_network.ps1', 'tools/watch_boot.py',
    'upstream/a523-bt-bsp/aic_hardware.c', 'upstream/a523-bt-bsp/SOURCES.json',
)
for name in source_names:
    save('sources/' + name, (root / name).read_bytes())
for name in ('peripheral-first-boot.json', 'peripheral-bundle-readback-reboot.txt',
             'peripheral-desktop-health.txt', 'desktop-periph1.png',
             'bluetooth-raw-init-autostart-reboot.json',
             'bluetooth-first-automatic-success-codec-error.txt',
             'bluetooth-stable-address-test.txt', 'bluetooth-autostart-real-scan.txt',
             'aligned-entry-emulation.json'):
    save('evidence/' + name, (root / 'evidence' / name).read_bytes())

readme = '''# periph1 桌面恢复基线

本包冻结已实际启动的 periph1 #2 内核、显示/触摸/无线/电池运行包及蓝牙模块。
它用于同一平板现有 Debian 根分区的引导/驱动恢复，不含当前桌面根分区镜像。
未包含未通过的音频候选；不要把此包理解为整机全部外设已适配。

验证边界：periph1 Image 和 bundle 已读回并多次启动；桌面已确认。
蓝牙原始初始化版本已通过开机自启及射频扫描；包内最新 CID 派生地址已读回并被
BlueZ 识别，但该地址版本的整机重启仍待确认。用户暂未做桌面触摸定位测试。

恢复运行包时顺序为：原基础 runtime-peripherals、periph1 graphics-runtime、
bluetooth-runtime。最后一步包含对 Wi-Fi 复位顺序的覆盖，不能被旧图形包覆盖。
每个运行包自带 FILES.json 和 install.py；内核 bundle 用现有精确 CID/GPT 更新工具。
TOC0 保留为已有引导的核对副本，无需重刷；禁止写 GPT 覆盖的 LBA16。

gfx1 回退必须同时恢复匹配的 gfx1 bundle 和 graphics-runtime，服务有版本条件。
最新现场状态和待办见工程 PROGRESS.md；此快照不说明设备此刻仍可远程连接。
'''
save('README.md', readme.encode('utf-8'))
record = {
    'kernel_release': '7.3.3-tzx-a523-periph1',
    'bundle_sha256': expected_bundle,
    'loader_sha256': expected_loader,
    'boot_verified': True,
    'boot_ids': [first_boot['linux_boot_id'], later_boot['linux_boot_id']],
    'package_files_verified': package_counts,
    'bluetooth_stable_address_runtime_verified': True,
    'bluetooth_stable_address_reboot_verified': False,
    'audio_included': False,
    'rootfs_included': False,
    'files': frozen,
}
(destination / 'FILES.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
for name, item in frozen.items():
    assert sha((destination / name).read_bytes()) == item['sha256']
print('PERIPH1_BASELINE_FROZEN', len(frozen), 'files;', package_counts)
