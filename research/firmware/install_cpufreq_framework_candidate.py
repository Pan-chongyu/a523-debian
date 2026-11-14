"""Stage #5 in an unused boot-gap slot; switch only the verified 512-byte header."""
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
parser.add_argument('--restore', action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert not Path('/sys/module/panfrost').exists()
if args.restore and Path('/var/lib/tzx/cpufreq-runtime-installed.json').exists():
    runtime = json.loads(Path('/var/lib/tzx/cpufreq-runtime-installed.json').read_text())
    for name, digest in runtime['files'].items():
        assert hashlib.sha256((Path('/') / name).read_bytes()).hexdigest() == digest
    subprocess.run(['systemctl', 'disable', '--now', 'tzx-cpufreq.service'], check=True)
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
assert not Path('/var/lib/tzx/gpu-qualified').exists()
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096

OLD_SHA = '32648d80d699892b3dcfe0be37fdc07a5ed30d95d8b9ad8cf2140bb6f3181799'
NEW_SHA = '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
OLD_CONFIG_SHA = 'd1b48cb2fd4a06cc02a188bc79aefeb63425dd27ad3b46896226e3061c0653ae'
NEW_CONFIG_SHA = 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3'
SIZE, OLD_SIZE, STORAGE_LBA = 14876672, 14809088, 65536
backup = Path('/root/tzx-recovery/cpufreq-framework')
config = Path('/boot/config-7.3.3-tzx-a523-accel1')
candidate = Path('/home/debian/cpufreq-framework-bundle.bin').read_bytes()
manifest = json.loads(Path('/home/debian/cpufreq-framework-bundle.json').read_text())
new_config = Path('/home/debian/cpufreq-framework.config').read_bytes()
assert len(candidate) == SIZE and hashlib.sha256(candidate).hexdigest() == NEW_SHA
assert manifest['sha256'] == NEW_SHA and manifest['start_lba'] == STORAGE_LBA
assert manifest['header_lba'] == 4096 and manifest['bytes'] == SIZE
assert hashlib.sha256(new_config).hexdigest() == NEW_CONFIG_SHA
header = bytearray(candidate[:512])
assert header[:8] == b'A523BND1' and struct.unpack_from('<II', header, 8) == (1, 5)
crc = struct.unpack_from('<I', header, 16)[0]
struct.pack_into('<I', header, 16, 0)
assert zlib.crc32(header) == crc
for index, item in enumerate(manifest['items']):
    lba, size, address, crc, _, _ = struct.unpack_from('<6I', candidate, 32 + index * 24)
    assert (lba, size, address) == (item['lba'], item['bytes'], int(item['load_address'], 16))
    offset = (lba - STORAGE_LBA) * 512
    rounded = (size + 511) & ~511
    assert 512 <= offset and offset + rounded <= SIZE and lba + rounded // 512 < 131072
    assert zlib.crc32(candidate[offset:offset + rounded]) == crc
    assert hashlib.sha256(candidate[offset:offset + size]).hexdigest() == item['sha256']

fd = os.open('/dev/mmcblk0', os.O_RDWR | os.O_SYNC)
try:
    gpt = os.pread(fd, 512, 512)
    assert gpt[:8] == b'EFI PART'
    assert str(uuid.UUID(bytes_le=gpt[56:72])) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    checked = bytearray(gpt)
    crc = struct.unpack_from('<I', checked, 16)[0]
    struct.pack_into('<I', checked, 16, 0)
    assert zlib.crc32(checked[:struct.unpack_from('<I', checked, 12)[0]]) == crc
    table_lba, entries, stride, table_crc = struct.unpack_from('<QIII', gpt, 72)
    assert 0 < entries * stride <= 65536
    table = os.pread(fd, entries * stride, table_lba * 512)
    assert zlib.crc32(table) == table_crc
    partitions = [table[n*stride:(n+1)*stride] for n in range(entries)
                  if any(table[n*stride:n*stride+16])]
    assert partitions and min(struct.unpack_from('<Q', p, 32)[0] for p in partitions) >= 131072
    current_header = os.pread(fd, 512, 4096 * 512)
    old_path = backup / 'bundle-before-cpufreq-framework.bin'
    config_path = backup / 'config-before-cpufreq-framework'
    if not args.restore:
        assert '#4 ' in os.uname().version
        old = os.pread(fd, OLD_SIZE, 4096 * 512)
        assert hashlib.sha256(old).hexdigest() == OLD_SHA
        assert hashlib.sha256(config.read_bytes()).hexdigest() == OLD_CONFIG_SHA
        backup.mkdir(parents=True, exist_ok=True)
        for path, data in ((old_path, old), (config_path, config.read_bytes())):
            if not path.exists():
                with path.open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        assert hashlib.sha256(old_path.read_bytes()).hexdigest() == OLD_SHA
        assert hashlib.sha256(config_path.read_bytes()).hexdigest() == OLD_CONFIG_SHA
        (backup / 'rollback.py').write_bytes(Path(__file__).read_bytes())
        # The running #4 payload occupies LBAs 4097..33019. Stage the new
        # independent payload at 65537 before replacing the common header.
        assert os.pwrite(fd, candidate, STORAGE_LBA * 512) == SIZE
        os.fsync(fd)
        assert hashlib.sha256(os.pread(fd, SIZE, STORAGE_LBA * 512)).hexdigest() == NEW_SHA
        assert hashlib.sha256(os.pread(fd, OLD_SIZE, 4096 * 512)).hexdigest() == OLD_SHA
        target_header = candidate[:512]
        target_config = new_config
    else:
        old = old_path.read_bytes()
        assert hashlib.sha256(old).hexdigest() == OLD_SHA
        assert hashlib.sha256(config_path.read_bytes()).hexdigest() == OLD_CONFIG_SHA
        assert current_header in (old[:512], candidate[:512])
        # Original payload was never overwritten; verify it before switching.
        assert os.pread(fd, OLD_SIZE - 512, 4097 * 512) == old[512:]
        target_header = old[:512]
        target_config = config_path.read_bytes()
    assert os.pwrite(fd, target_header, 4096 * 512) == 512
    os.fsync(fd)
    assert os.pread(fd, 512, 4096 * 512) == target_header
    # Check each selected payload at its actual LBA, not just the staged file.
    target_image = old if args.restore else candidate
    base = 4096 if args.restore else STORAGE_LBA
    for index in range(5):
        lba, length, _, crc, _, _ = struct.unpack_from('<6I', target_image, 32 + index * 24)
        rounded = (length + 511) & ~511
        actual = os.pread(fd, rounded, lba * 512)
        assert zlib.crc32(actual) == crc
        offset = (lba - base) * 512
        assert actual == target_image[offset:offset+rounded]
    assert os.pread(fd, 512, 512) == gpt
finally:
    os.close(fd)

if args.restore:
    mirror_backup = Path('/root/tzx-recovery/cpufreq-boot-mirrors')
    if (mirror_backup / 'before.json').exists():
        previous = json.loads((mirror_backup / 'before.json').read_text())
        current_state = json.loads(Path('/var/lib/tzx/cpufreq-framework-installed.json').read_text())
        expected = current_state['mirror_sha256']
        assert set(previous) == set(expected)
        for name, digest in previous.items():
            path = Path(name)
            assert not path.is_symlink()
            if path.exists():
                assert hashlib.sha256(path.read_bytes()).hexdigest() in (digest, expected[name])
            if digest is not None:
                assert hashlib.sha256((mirror_backup / name.lstrip('/')).read_bytes()).hexdigest() == digest
        for name, digest in previous.items():
            path = Path(name)
            if digest is None:
                path.unlink(missing_ok=True)
            else:
                temporary = path.with_name(path.name + '.cpufreq-mirror-restore')
                temporary.write_bytes((mirror_backup / name.lstrip('/')).read_bytes())
                temporary.replace(path)

temporary = config.with_name(config.name + '.cpufreq-new')
temporary.write_bytes(target_config)
temporary.chmod(config.stat().st_mode & 0o777)
temporary.replace(config)
record = dict(state='restored_4_reboot_pending' if args.restore else 'framework_5_installed_reboot_pending',
              old_bundle_sha256=OLD_SHA, new_bundle_sha256=NEW_SHA,
              boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              storage_lba=STORAGE_LBA, header_lba=4096, cpufreq_driver_autostart=False)
state = Path('/var/lib/tzx/cpufreq-framework-installed.json')
state.parent.mkdir(parents=True, exist_ok=True)
state.write_text(json.dumps(record, indent=2) + '\n')
os.sync()
print('CPUFREQ_FRAMEWORK_HEADER_AND_EVERY_PAYLOAD_FULL_READBACK_PASS', json.dumps(record), flush=True)
subprocess.run(['systemd-run', '--unit=tzx-cpufreq-framework-' + ('restore' if args.restore else 'trial') + '-reboot',
                '--on-active=3s', '/usr/bin/systemctl', 'reboot'], check=True)
