"""Stage a pinned #8 diagnostic bundle and switch one header; retain #5 intact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid
import zlib

parser = argparse.ArgumentParser()
parser.add_argument('--activate', action='store_true')
parser.add_argument('--restore', action='store_true')
args = parser.parse_args()
assert not (args.activate and args.restore)
assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not Path('/sys/module/panfrost').exists()
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert any(build in os.uname().version for build in ('#5 ', '#8 '))
if not args.restore:
    assert '#5 ' in os.uname().version

OLD_SHA = '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
NEW_SHA = '41dd2f3ed142844964a344a1fedadf8833c3a0e85df641f9b0ec18f10d504ebd'
CONFIG_SHA = 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3'
TOC0_SHA = 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
OLD_LBA, OLD_SIZE, NEW_LBA, NEW_SIZE = 65536, 14876672, 98304, 14876672
sha = lambda data: hashlib.sha256(data).hexdigest()
folder = Path('/home/debian/mmc-dma-kernel')
candidate = (folder/'linux-bundle.bin').read_bytes()
manifest = json.loads((folder/'linux-bundle.json').read_text())
new_config = (folder/'kernel.config').read_bytes()
assert len(candidate) == NEW_SIZE and sha(candidate) == NEW_SHA
assert sha(new_config) == CONFIG_SHA
assert (manifest['sha256'], manifest['start_lba'], manifest['header_lba'], manifest['bytes']) == (NEW_SHA, NEW_LBA, 4096, NEW_SIZE)
backup = Path('/root/tzx-recovery/mmc-dma-kernel')
old_expected = {
    '/boot/Image': '6c2b8b6492a26c1f8783d0503314b8700535ed690eea63476a09dab38a769ce5',
    '/home/debian/current-bundle/Image': '6c2b8b6492a26c1f8783d0503314b8700535ed690eea63476a09dab38a769ce5',
    '/boot/board.dtb': 'a2721370964d3eb1f80a4b3a46be562852578e3055e3ff4169e2563852d0b791',
    '/home/debian/current-bundle/board.dtb': 'a2721370964d3eb1f80a4b3a46be562852578e3055e3ff4169e2563852d0b791',
    '/boot/initramfs.cpio.gz': '783d3b9d11f4f59606ac50e4cb0c36ac7ca6ac3d05d227202624cc05bcbe397c',
    '/home/debian/current-bundle/initramfs.cpio.gz': '783d3b9d11f4f59606ac50e4cb0c36ac7ca6ac3d05d227202624cc05bcbe397c',
    '/boot/kernel.config': 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3',
    '/boot/config-7.3.3-tzx-a523-accel1': 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3',
    '/home/debian/installed-bundle.json': 'eb0a03a538878ba5ca615861d19aef4d977924e590106ab969313e3cec3c83ef',
}


def atomic(path, data):
    assert not path.is_symlink(), path
    temporary = path.with_name(path.name+'.mmc-dma-new')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
    temporary.replace(path)
    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def validate_bundle(data, base):
    header = bytearray(data[:512])
    assert header[:8] == b'A523BND1' and struct.unpack_from('<II', header, 8) == (1, 5)
    crc = struct.unpack_from('<I', header, 16)[0]
    struct.pack_into('<I', header, 16, 0)
    assert zlib.crc32(header) == crc
    end = 512
    for index, address in enumerate((0x48080000, 0x47000000, 0x60000000, 0x4a000000, 0x54000)):
        lba, length, load, crc, reserved1, reserved2 = struct.unpack_from('<6I', data, 32+index*24)
        offset, rounded = (lba-base)*512, (length+511) & ~511
        assert length > 0 and load == address and reserved1 == reserved2 == 0
        assert offset == end and offset+rounded <= len(data)
        assert lba+rounded//512 < 131072
        assert zlib.crc32(data[offset:offset+rounded]) == crc
        end = offset+rounded
    assert end == len(data)


validate_bundle(candidate, NEW_LBA)
new_contents = {}
for index, item in enumerate(manifest['items']):
    lba, length, address = struct.unpack_from('<3I', candidate, 32+index*24)
    assert (lba, length, address) == (item['lba'], item['bytes'], int(item['load_address'], 16))
    offset = (item['lba']-NEW_LBA)*512
    data = candidate[offset:offset+item['bytes']]
    assert sha(data) == item['sha256']
    new_contents[item['file']] = data
assert set(new_contents) == {'Image', 'board.dtb', 'initramfs.cpio.gz', 'linux-entry.bin', 'bl31.bin'}
assert new_contents['Image'][:4] and sha(new_contents['Image']) == '9fe18fff01f197a2cf9d03ab33408c3c4f16fd061602eb5b3c8cae38bd2d5ff1'
new_mirrors = {name: (new_config if name.startswith('/boot/') and ('config' in Path(name).name)
                      else json.dumps(manifest, indent=2).encode()+b'\n' if name.endswith('installed-bundle.json')
                      else new_contents[Path(name).name]) for name in old_expected}
new_expected = {name: sha(data) for name, data in new_mirrors.items()}

fd = os.open('/dev/mmcblk0', os.O_RDWR | os.O_SYNC)
try:
    toc0 = os.pread(fd, 40960, 256*512)
    assert sha(toc0) == TOC0_SHA
    gpt = os.pread(fd, 512, 512)
    assert gpt[:8] == b'EFI PART'
    assert str(uuid.UUID(bytes_le=gpt[56:72])) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    checked = bytearray(gpt)
    crc = struct.unpack_from('<I', checked, 16)[0]
    struct.pack_into('<I', checked, 16, 0)
    assert zlib.crc32(checked[:struct.unpack_from('<I', checked, 12)[0]]) == crc
    table_lba, entries, stride, table_crc = struct.unpack_from('<QIII', gpt, 72)
    assert 0 < entries*stride <= 65536 and stride >= 128
    table = os.pread(fd, entries*stride, table_lba*512)
    assert zlib.crc32(table) == table_crc
    starts = [struct.unpack_from('<Q', table, n*stride+32)[0] for n in range(entries)
              if any(table[n*stride:n*stride+16])]
    assert starts and min(starts) == 131072
    assert OLD_LBA+OLD_SIZE//512 < NEW_LBA and NEW_LBA+NEW_SIZE//512 < min(starts)
    old = os.pread(fd, OLD_SIZE, OLD_LBA*512)
    assert sha(old) == OLD_SHA
    validate_bundle(old, OLD_LBA)
    active = os.pread(fd, 512, 4096*512)
    assert active in ((old[:512], candidate[:512]) if args.restore else (old[:512],))

    if not args.restore:
        for name, digest in old_expected.items():
            path = Path(name)
            assert not path.is_symlink() and sha(path.read_bytes()) == digest, name
        backup.mkdir(parents=True, exist_ok=True)
        saved = {'active-header.bin': old[:512], 'installer.py': Path(__file__).read_bytes()}
        saved.update({name.lstrip('/'): Path(name).read_bytes() for name in old_expected})
        for name, data in saved.items():
            path = backup/name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                atomic(path, data)
            assert path.read_bytes() == data, path
        prior_spare = os.pread(fd, 14876672, NEW_LBA*512)
        assert sha(prior_spare) in ('0d9c3e238b5910f299c24d9c09d2a759e06076756150f5560a0f8af3148da985', NEW_SHA)
        os.sync()
        assert os.pwrite(fd, candidate, NEW_LBA*512) == len(candidate)
        os.fsync(fd)
        assert sha(os.pread(fd, NEW_SIZE, NEW_LBA*512)) == NEW_SHA
        assert sha(os.pread(fd, OLD_SIZE, OLD_LBA*512)) == OLD_SHA
        print('MMC_DMA_STAGED_FULL_READBACK_PASS_OLD_SLOT_UNCHANGED', NEW_SHA, flush=True)
        if args.activate:
            subprocess.run(['systemctl', 'disable', '--now', 'tzx-cpufreq.service'], check=True, timeout=45)
            assert not Path('/sys/module/tzx_cpufreq_divider').exists()
            for name, data in new_mirrors.items():
                atomic(Path(name), data)
            target_header = candidate[:512]
    else:
        assert (backup/'active-header.bin').read_bytes() == old[:512]
        for name, digest in old_expected.items():
            original = backup/name.lstrip('/')
            assert sha(original.read_bytes()) == digest
            assert sha(Path(name).read_bytes()) in (digest, new_expected[name]), name
        for name in old_expected:
            atomic(Path(name), (backup/name.lstrip('/')).read_bytes())
        subprocess.run(['systemctl', 'enable', 'tzx-cpufreq.service'], check=True, timeout=20)
        target_header = old[:512]

    if args.activate or args.restore:
        assert os.pwrite(fd, target_header, 4096*512) == 512
        os.fsync(fd)
        assert os.pread(fd, 512, 4096*512) == target_header
        selected, base = (old, OLD_LBA) if args.restore else (candidate, NEW_LBA)
        for index in range(5):
            lba, length, _, _, _, _ = struct.unpack_from('<6I', selected, 32+index*24)
            rounded = (length+511) & ~511
            offset = (lba-base)*512
            assert os.pread(fd, rounded, lba*512) == selected[offset:offset+rounded]
        for name, digest in (old_expected if args.restore else new_expected).items():
            assert sha(Path(name).read_bytes()) == digest, name
    assert os.pread(fd, 40960, 256*512) == toc0
    assert os.pread(fd, 512, 512) == gpt
    assert os.pread(fd, len(table), table_lba*512) == table
finally:
    os.close(fd)

record = {'state': 'restored_5_reboot_pending' if args.restore else 'diagnostic_8_reboot_pending' if args.activate else 'staged_only',
          'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'bundle_sha256': OLD_SHA if args.restore else NEW_SHA, 'gpu_autostart': False,
          'retained_5_slot_lba': OLD_LBA, 'diagnostic_8_slot_lba': NEW_LBA,
          'mirror_sha256': old_expected if args.restore else new_expected}
state = Path('/var/lib/tzx/mmc-dma-kernel.json')
state.parent.mkdir(parents=True, exist_ok=True)
atomic(state, json.dumps(record, indent=2).encode()+b'\n')
os.sync()
print('MMC_DMA_INSTALL_STATE', json.dumps(record), flush=True)
if args.activate or args.restore:
    subprocess.run(['systemd-run', '--unit=tzx-mmc-dma-'+('restore' if args.restore else 'activate')+'-reboot',
                    '--on-active=3s', '/usr/bin/systemctl', 'reboot'], check=True, timeout=20)
