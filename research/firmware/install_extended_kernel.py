"""Stage and select the additive swap/video kernel with a pinned intact rollback slot."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid
import zlib

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('verify', 'stage', 'activate', 'restore', 'verify-boot'))
a = p.parse_args()
assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
sha = lambda b: hashlib.sha256(b).hexdigest()
OLD = 'f6b644da1a8276b599c9e3f6b7944c6eb246ddd8c8adf0cbe5ba20116c6a3829'
NEW = '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'
TOC = '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
CONFIG = '59cc725631e95f3726080322e19f4868ef461035e85d6f7dd02b5be2915aced6'
folder = Path('/home/debian/extended-kernel')
backup = Path('/root/tzx-recovery/extended-kernel')
state_path = Path('/var/lib/tzx/extended-kernel-installed.json')
manifest_data = (folder/'linux-bundle.json').read_bytes()
manifest = json.loads(manifest_data)
candidate = (folder/'linux-bundle.bin').read_bytes()
config = (folder/'kernel.config').read_bytes()
assert sha(candidate) == manifest['sha256'] == NEW and len(candidate) == manifest['bytes'] == 15008768
assert sha(config) == manifest['config_sha256'] == CONFIG
assert (manifest['start_lba'], manifest['header_lba']) == (65536, 4096)
assert manifest['config_change'] == 'SWAP, ZRAM/LZ4, DMA_HEAP_SYSTEM, sun55i IOMMU for VE0/VE1 only'
assert 65536+len(candidate)//512 < 98304


def atomic(path, data, mode=None):
    assert not path.is_symlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    temp = path.with_name(path.name+'.screenboot-new')
    with temp.open('wb') as stream:
        stream.write(data)
        os.fchmod(stream.fileno(), mode)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def record(path, value):
    atomic(path, (json.dumps(value, indent=2)+'\n').encode())


def payloads(bundle, start):
    assert bundle[:8] == b'A523BND1' and struct.unpack_from('<II', bundle, 8) == (1, 5)
    checked = bytearray(bundle[:512])
    checksum = struct.unpack_from('<I', checked, 16)[0]
    struct.pack_into('<I', checked, 16, 0)
    assert zlib.crc32(checked) == checksum
    result = []
    for i in range(5):
        lba, length, address, crc, r1, r2 = struct.unpack_from('<6I', bundle, 32+i*24)
        assert r1 == r2 == 0
        offset = (lba-start)*512
        padded = bundle[offset:offset+((length+511)&~511)]
        assert offset >= 512 and len(padded) == (length+511)&~511
        assert zlib.crc32(padded) == crc
        result.append((lba, length, address, padded[:length]))
    return result


write = a.operation in ('stage', 'activate', 'restore')
fd = os.open('/dev/mmcblk0', os.O_RDWR|os.O_SYNC if write else os.O_RDONLY)
try:
    toc = os.pread(fd, 40960, 256*512)
    assert sha(toc) == TOC
    primary = os.pread(fd, 34*512, 0)
    secondary = os.pread(fd, 33*512, (244318208-33)*512)
    gpt = bytearray(primary[512:1024])
    assert gpt[:8] == b'EFI PART' and str(uuid.UUID(bytes_le=bytes(gpt[56:72]))) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    checksum = struct.unpack_from('<I', gpt, 16)[0]
    struct.pack_into('<I', gpt, 16, 0)
    assert zlib.crc32(gpt[:struct.unpack_from('<I', gpt, 12)[0]]) == checksum
    table_lba, count, stride, crc = struct.unpack_from('<QIII', gpt, 72)
    assert 0 < count*stride <= 65536
    table = os.pread(fd, count*stride, table_lba*512)
    assert zlib.crc32(table) == crc
    starts = [struct.unpack_from('<Q', table, i*stride+32)[0] for i in range(count)
              if any(table[i*stride:i*stride+16])]
    assert min(starts) == 131072
    old = os.pread(fd, 14942208, 98304*512)
    assert sha(old) == OLD
    old_parts, new_parts = payloads(old, 98304), payloads(candidate, 65536)
    for i, (item, part) in enumerate(zip(manifest['items'], new_parts)):
        assert (item['lba'], item['bytes'], int(item['load_address'], 16), item['sha256']) == (*part[:3], sha(part[3]))
        assert part[2] == old_parts[i][2]
        if i in (2, 4): assert part[3] == old_parts[i][3]
    active = os.pread(fd, 512, 4096*512)
    assert active in (old[:512], candidate[:512])
    mirrors = {'/home/debian/installed-bundle.json': manifest_data,
               '/boot/kernel.config': config, '/boot/config-7.3.3-tzx-a523-accel1': config}
    for item, part in zip(manifest['items'][:3], new_parts[:3]):
        for parent in ('/boot', '/home/debian/current-bundle'):
            mirrors[str(Path(parent)/item['file'])] = part[3]
    if a.operation == 'stage':
        assert active == old[:512] and not backup.exists()
        assert sha(gzip.decompress(Path('/proc/config.gz').read_bytes())) == '428ec704c7c2e2d1a457dd421f232ed2082850229900f67bc1902c49fb92cf59'
        subprocess.run(['python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'], check=True, timeout=30)
        backup.mkdir(parents=True)
        atomic(backup/'active-header.bin', active)
        atomic(backup/'spare-slot-before.bin', os.pread(fd, len(candidate), 65536*512))
        before = {}
        for name in mirrors:
            path = Path(name)
            data = path.read_bytes()
            atomic(backup/'files'/name.lstrip('/'), data, path.stat().st_mode & 0o777)
            before[name] = {'sha256': sha(data), 'mode': path.stat().st_mode & 0o777}
        record(backup/'before.json', {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'files': before})
        assert os.pwrite(fd, candidate, 65536*512) == len(candidate)
        os.fsync(fd)
        assert os.pread(fd, len(candidate), 65536*512) == candidate
        print('EXTENDED_KERNEL_STAGED_COMPLETE_READBACK_PASS', NEW, flush=True)
    if a.operation in ('activate', 'restore'):
        assert (backup/'active-header.bin').read_bytes() == old[:512]
        before = json.loads((backup/'before.json').read_text())
        assert os.pread(fd, len(candidate), 65536*512) == candidate
        if a.operation == 'activate':
            assert active == old[:512]
            target = candidate
            for name, data in mirrors.items(): atomic(Path(name), data)
        else:
            target = old
            for name, item in before['files'].items():
                data = (backup/'files'/name.lstrip('/')).read_bytes()
                assert sha(data) == item['sha256']
                atomic(Path(name), data, item['mode'])
        assert os.pwrite(fd, target[:512], 4096*512) == 512
        os.fsync(fd)
        assert os.pread(fd, 512, 4096*512) == target[:512]
        record(state_path, {'state': 'selected_pending_reboot' if a.operation == 'activate' else 'restored_original',
                           'selected_bundle_sha256': NEW if a.operation == 'activate' else OLD,
                           'previous_bundle_sha256': OLD, 'config_sha256': CONFIG,
                           'installed_boot_id': before['boot_id'], 'backup': str(backup)})
        print('EXTENDED_KERNEL_HEADER_SELECTED_AND_MIRRORS_SYNCED', a.operation, flush=True)
    if a.operation == 'verify-boot':
        assert active == candidate[:512]
        assert os.pread(fd, len(candidate), 65536*512) == candidate
        assert sha(gzip.decompress(Path('/proc/config.gz').read_bytes())) == CONFIG
        assert Path('/sys/class/graphics/fbcon/rotate').read_text().strip() == '1'
        for name, data in mirrors.items(): assert Path(name).read_bytes() == data, name
        state = json.loads(state_path.read_text())
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert boot != state['installed_boot_id']
        subprocess.run(['python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'], check=True, timeout=30)
        state.update(state='actual_boot_verified', verified_boot_id=boot, fbcon_rotation='clockwise', module_abi='recompiled_allocatable_code_data_compared; MODVERSIONS_disabled')
        record(state_path, state)
        print('EXTENDED_KERNEL_ACTUAL_BOOT_ROTATED_CONSOLE_PASS', json.dumps(state), flush=True)
    assert os.pread(fd, 14942208, 98304*512) == old
    assert os.pread(fd, 40960, 256*512) == toc
    assert os.pread(fd, len(primary), 0) == primary
    assert os.pread(fd, len(secondary), (244318208-33)*512) == secondary
finally:
    os.close(fd)
os.sync()
print('EXTENDED_KERNEL_GPT_TRAINED_LOADER_AND_ORIGINAL_SLOT_UNCHANGED', flush=True)
