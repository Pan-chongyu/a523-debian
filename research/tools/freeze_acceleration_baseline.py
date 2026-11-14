"""Freeze the boot-tested accel1 image, runtime packages and evidence."""
import hashlib
import json
from pathlib import Path
import struct
import tarfile
import zlib

root = Path(__file__).resolve().parents[1]
source = root/'build/acceleration-kernel'
destination = root/'build/accel1-desktop-verified'
expected = 'be5f7622a867eb1136b5bda8863e199503ef9f5dcc2ca3d192109270ed58d07a'


def sha(data):
    return hashlib.sha256(data).hexdigest()


bundle = (source/'linux-bundle.bin').read_bytes()
metadata = json.loads((source/'linux-bundle.json').read_text())
assert sha(bundle) == expected == metadata['sha256']
assert len(bundle) == metadata['bytes'] == metadata['sectors']*512
assert metadata['start_lba'] == 4096 and bundle[:8] == b'A523BND1'
assert struct.unpack_from('<II', bundle, 8) == (1, 5)
header = bytearray(bundle[:512])
crc = struct.unpack_from('<I', header, 16)[0]
struct.pack_into('<I', header, 16, 0)
assert zlib.crc32(header) == crc
payloads = {}
end = 512
for index, item in enumerate(metadata['items']):
    lba, size, address, crc, r1, r2 = struct.unpack_from('<6I', bundle, 32+index*24)
    assert (lba, size, address) == (item['lba'], item['bytes'], int(item['load_address'], 16))
    assert r1 == r2 == 0 and Path(item['file']).name == item['file']
    start = (lba-4096)*512
    rounded = (size+511)&~511
    assert start == end and start+rounded <= len(bundle)
    assert zlib.crc32(bundle[start:start+rounded]) == crc
    data = bundle[start:start+size]
    assert sha(data) == item['sha256']
    payloads['boot/'+item['file']] = data
    end = start+rounded
assert end == len(bundle) and 4096+len(bundle)//512 < 131072
assert 'UPDATED_BUNDLE_FULL_READBACK_PASS:'+expected in (root/'evidence/acceleration-bundle-readback-reboot.txt').read_text()
assert 'ACCEL_INSTALLED_HASHES_PASS 80' in (root/'evidence/acceleration-baseline-installed-verification.txt').read_text()
boots = []
for name in ['acceleration-first-boot.json', 'acceleration-autostart-reboot.json']:
    record = json.loads((root/'evidence'/name).read_text())
    assert record['state'] == 'SSH_READY' and '7.3.3-tzx-a523-accel1 #2' in record['linux_identity']
    boots.append(record['linux_boot_id'])
assert len(set(boots)) == 2
metadata['verified_boot_ids'] = boots
metadata['verification_evidence'] += ['evidence/acceleration-autostart-reboot.json', 'evidence/acceleration-baseline-installed-verification.txt']
(source/'linux-bundle.json').write_text(json.dumps(metadata, indent=2)+'\n')

packages = [
    ('build/acceleration-kernel/acceleration-runtime.tar.gz', 'acceleration-runtime.json'),
    ('build/acceleration-hardware/acceleration-hardware.tar.gz', 'acceleration-hardware.json')]
for name, metadata_name in packages:
    path = root/name
    item = json.loads((path.parent/metadata_name).read_text())
    assert sha(path.read_bytes()) == item['archive_sha256']
    with tarfile.open(path) as archive:
        assert len(archive.getnames()) == len(set(archive.getnames()))
        assert json.load(archive.extractfile('FILES.json')) == item['files']
        for member, digest in item['files'].items():
            assert not Path(member).is_absolute() and '..' not in Path(member).parts
            assert sha(archive.extractfile(member).read()) == digest
        compile(archive.extractfile('install.py').read(), 'install.py', 'exec')
    item['autostart_reboot_verified'] = True
    item['verified_boot_id'] = boots[-1]
    (path.parent/metadata_name).write_text(json.dumps(item, indent=2)+'\n')

destination.mkdir(exist_ok=False)
files = {}


def save(name, data):
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    path = destination/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    files[name] = {'sha256': sha(data), 'bytes': len(data)}


for name, data in payloads.items():
    save(name, data)
names = ['build/known-good-loader/chain-loader.toc0',
         'build/runtime-peripherals.tar.gz',
         'build/peripheral-kernel/graphics-runtime.tar.gz',
         'build/peripheral-kernel/bluetooth-runtime.tar.gz',
         'build/audio-codec/audio-runtime.tar.gz',
         'build/verify_acceleration_install.py',
         'PROGRESS.md', 'GPU-THERMAL-INTEGRATION.md', 'AUDIO-INTEGRATION.md']
for directory in ['build/acceleration-kernel', 'build/acceleration-hardware',
                  'build/thermal-acceleration', 'build/gpu-acceleration']:
    names += [p.relative_to(root).as_posix() for p in (root/directory).iterdir() if p.is_file()]
names += [p.relative_to(root).as_posix() for p in (root/'firmware').iterdir() if p.is_file() and p.suffix in ['.c', '.h', '.S', '.dts']]
names += ['firmware/'+name for name in ['tzx-acceleration-hardware', 'verify_gpu_render.py',
          'verify_thermal_sensors.py', 'verify_gpu_workload.py', '30-tzx-acceleration.conf',
          'tzx-mesa-kmsro.conf', 'tzx-display-runtime', 'tzx-audio-runtime']]
names += ['tools/'+name for name in ['build_acceleration_kernel.sh', 'build_acceleration_modules.sh',
          'build_thermal.sh', 'prepare_thermal_port.py', 'build_gpu_overlay.sh', 'build_display_power.sh',
          'package_acceleration_runtime.py', 'package_acceleration_hardware.py',
          'make_bundle_update.py', 'make_bundle_variant.py', 'verify_aligned_entry.py',
          'ensure_usb_network.ps1', 'watch_boot.py', 'freeze_acceleration_baseline.py']]
names += ['evidence/'+name for name in ['acceleration-first-boot.json',
          'acceleration-bundle-readback-reboot.txt', 'acceleration-autostart-reboot.json',
          'accelerated-desktop-reboot-final-check.txt', 'acceleration-baseline-installed-verification.txt',
          'acceleration-user-confirmation.json', 'gpu-first-shader-readback.txt',
          'gpu-kmsro-display-node-readback.txt', 'desktop-gpu-second-trial-result.txt',
          'thermal-response-and-gpu-power-provider.txt', 'gpu-workload-and-lradc-clock.txt',
          'acceleration-aligned-entry-emulation.json']]
for name in sorted(set(names)):
    save(name, (root/name).read_bytes())
save('README.md', '''# accel1 实机验证基线

本包针对同一台 TZX P30，CID 3e01ff55454d20202010209170281b59。
包含已读回并启动两次的 accel1 #2 引导及匹配运行包，不含完整根分区。
用户确认 GPU 加速后的桌面和触摸正常。CPU DVFS、整机休眠及其余待办未完成。

恢复前保留现有根分区；TOC0 已有核对副本，通常无需重刷，禁止写 LBA16。
需要先有 periph1 基础服务。首次恢复的顺序为：runtime-peripherals、periph1
graphics-runtime、bluetooth-runtime、audio-runtime，再安装 acceleration-runtime。
然后通过精确 CID/容量/GPT 更新器安装本包 bundle 并启动 accel1，最后安装
acceleration-hardware、检查哈希与所有服务。两个 accel1 包都自带 install.py。
重装 acceleration-runtime 会覆盖 generator overrides，必须随后重装硬件包。

平板 /root/tzx-recovery/periph1/linux-bundle.bin 保留原 periph1 内核。
generator 只在 accel1 下覆盖路径，periph1 保持原软件桌面及音频恢复能力。
不要仅替换 Image 或任意混用不同内核的模块；详细验证及限制见随包文档。
'''.encode())
record = {'kernel_release': '7.3.3-tzx-a523-accel1', 'bundle_sha256': expected,
          'boot_ids': boots, 'gpu_glamor_reboot_verified': True, 'thermal_reboot_verified': True,
          'user_desktop_touch_confirmed': True, 'rootfs_included': False, 'files': files}
(destination/'FILES.json').write_text(json.dumps(record, indent=2)+'\n')
for name, item in files.items():
    assert sha((destination/name).read_bytes()) == item['sha256']
archive = destination.with_suffix('.tar.gz')
with tarfile.open(archive, 'w:gz') as package:
    package.add(destination, arcname=destination.name)
result = {'archive': archive.name, 'bytes': archive.stat().st_size,
          'sha256': sha(archive.read_bytes()), 'files': len(files)}
(archive.parent/(archive.name+'.json')).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
