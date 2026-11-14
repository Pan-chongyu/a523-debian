"""Pinned pre-training voltage diagnostic; never writes PMIC from Linux."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid
import zlib

p = argparse.ArgumentParser()
mode = p.add_mutually_exclusive_group()
mode.add_argument('--activate', action='store_true')
mode.add_argument('--restore', action='store_true')
a = p.parse_args()
sha = lambda data: hashlib.sha256(data).hexdigest()
OLD = 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
NEW = '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
OLD_RUNTIME = 'b1045903561eca454a7e9fe8158d5df29de37047ec31a2555a0dfb986a005738'
NEW_RUNTIME = 'e1f7beb91db90ac8443dc46fff846754f4d34d7ca6d6dc63f8e5c481e39e2f44'
BUNDLE = '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
SPARE = '41dd2f3ed142844964a344a1fedadf8833c3a0e85df641f9b0ec18f10d504ebd'
folder = Path('/home/debian/dram-boot-voltage')
backup = Path('/root/tzx-recovery/dram-boot-voltage')
runtime = Path('/usr/local/lib/tzx-rtc-context/runtime.py')
retired = [
    'tzx-dram-c-step-1200.service', 'tzx-dram-c-step-boot-restore.service',
    'tzx-dram-step-1200.service', 'tzx-dram-step-boot-restore.service',
    'tzx-dram-rail-baseline.service', 'tzx-dram-rail-nominal.service',
]


def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data, permissions=0o600):
    assert not path.is_symlink(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.dram-boot-new')
    with temporary.open('wb') as f:
        f.write(data)
        f.flush()
        os.fchmod(f.fileno(), permissions)
        os.fchown(f.fileno(), 0, 0)
        os.fsync(f.fileno())
    temporary.replace(path)
    syncdir(path.parent)
    assert path.read_bytes() == data, path


def save(name, data):
    path = backup/name
    if not path.exists():
        atomic(path, data)
    assert path.read_bytes() == data, path


def run(*args):
    return subprocess.run(args, check=True, timeout=40, text=True, capture_output=True).stdout.strip()


assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1]) > 3900000
assert not Path('/var/lib/tzx/gpu-qualified').exists()
for name in ('panfrost', 'tzx_cpufreq_divider'):
    assert not Path('/sys/module', name).exists(), name
assert run('systemctl', 'is-active', 'tzx-rtc-log.service') == 'active'
candidate = (folder/'loader.toc0').read_bytes()
new_runtime = (folder/'rtc-context-runtime.py').read_bytes()
assert len(candidate) == 40960 and candidate[:8] == b'TOC0.GLH' and sha(candidate) == NEW
assert sha(new_runtime) == NEW_RUNTIME
compile(new_runtime, 'rtc-context-runtime.py', 'exec')
current_runtime = runtime.read_bytes()
assert sha(current_runtime) in ((OLD_RUNTIME, NEW_RUNTIME) if a.restore else (OLD_RUNTIME,))
mirrors = {
    '/boot/Image': '6c2b8b6492a26c1f8783d0503314b8700535ed690eea63476a09dab38a769ce5',
    '/boot/board.dtb': 'a2721370964d3eb1f80a4b3a46be562852578e3055e3ff4169e2563852d0b791',
    '/boot/initramfs.cpio.gz': '783d3b9d11f4f59606ac50e4cb0c36ac7ca6ac3d05d227202624cc05bcbe397c',
    '/boot/kernel.config': 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3',
    '/boot/config-7.3.3-tzx-a523-accel1': 'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3',
    '/home/debian/installed-bundle.json': 'eb0a03a538878ba5ca615861d19aef4d977924e590106ab969313e3cec3c83ef',
}
for name, digest in mirrors.items():
    assert sha(Path(name).read_bytes()) == digest, name

fd = os.open('/dev/mmcblk0', os.O_RDWR | os.O_SYNC)
try:
    before = os.pread(fd, 65536, 0)
    ending = os.pread(fd, 33*512, (244318208-33)*512)
    header = bytearray(before[512:1024])
    assert header[:8] == b'EFI PART'
    assert str(uuid.UUID(bytes_le=bytes(header[56:72]))) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    crc = struct.unpack_from('<I', header, 16)[0]
    struct.pack_into('<I', header, 16, 0)
    assert zlib.crc32(header[:struct.unpack_from('<I', header, 12)[0]]) == crc
    table_lba, count, stride, crc = struct.unpack_from('<QIII', header, 72)
    assert stride >= 128 and 0 < count*stride <= 65536
    table = os.pread(fd, count*stride, table_lba*512)
    assert zlib.crc32(table) == crc
    starts = [struct.unpack_from('<Q', table, i*stride+32)[0] for i in range(count)
              if any(table[i*stride:i*stride+16])]
    assert starts and min(starts) == 131072
    old_bundle = os.pread(fd, 14876672, 65536*512)
    assert sha(old_bundle) == BUNDLE
    active = os.pread(fd, 4096, 4096*512)
    assert active[:512] == old_bundle[:512]
    assert sha(os.pread(fd, 14876672, 98304*512)) == SPARE
    current = os.pread(fd, 40960, 256*512)
    assert sha(current) in ((OLD, NEW) if a.restore else (OLD,))
    if a.restore:
        original = (backup/'original.toc0').read_bytes()
        original_runtime = (backup/'rtc-context-runtime.py').read_bytes()
        assert len(original) == 40960 and sha(original) == OLD
        assert sha(original_runtime) == OLD_RUNTIME
    else:
        original, original_runtime = current, current_runtime
    print('DRAM_BOOT_VOLTAGE_PREFLIGHT_PASS', json.dumps({
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'current_toc0': sha(current), 'candidate_toc0': NEW,
        'kernel_bundle_unchanged': BUNDLE, 'gpt_crc': 'PASS',
        'pmic_writes_from_linux': 0}), flush=True)

    if a.activate or a.restore:
        if a.activate:
            backup.mkdir(parents=True, exist_ok=True)
            syncdir(backup.parent)
            save('original.toc0', original)
            save('rtc-context-runtime.py', original_runtime)
            save('installer.py', Path(__file__).read_bytes())
            # Retire all live-voltage units. In particular, the old boot restore
            # must never lower the rail after this new training has completed.
            for name in retired:
                unit = Path('/etc/systemd/system', name)
                if not unit.is_symlink():
                    save(name, unit.read_bytes())
                enabled = subprocess.run(['systemctl', 'is-enabled', name], text=True, capture_output=True)
                if enabled.stdout.strip() != 'masked':
                    subprocess.run(['systemctl', 'disable', name], check=True, timeout=30,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                link = unit.with_name(unit.name+'.dram-boot-mask')
                if link.is_symlink():
                    link.unlink()
                assert not link.exists()
                os.symlink('/dev/null', link)
                link.replace(unit)
                syncdir(unit.parent)
            run('systemctl', 'daemon-reload')
            for name in retired:
                result = subprocess.run(['systemctl', 'is-enabled', name], text=True, capture_output=True)
                assert result.stdout.strip() == 'masked', (name, result.stdout)
                assert run('systemctl', 'show', name, '-p', 'ActiveState', '--value') in ('inactive', 'failed')
            syncdir(Path('/etc/systemd/system/multi-user.target.wants'))
        run('systemctl', 'disable', '--now', 'tzx-cpufreq.service')
        assert not Path('/sys/module/tzx_cpufreq_divider').exists()
        target = original if a.restore else candidate
        target_runtime = original_runtime if a.restore else new_runtime
        atomic(runtime, target_runtime, 0o755)
        os.sync()
        try:
            assert os.pwrite(fd, target, 256*512) == 40960
            os.fsync(fd)
            assert os.pread(fd, 40960, 256*512) == target
            assert os.pread(fd, 65536, 0) == before
            assert os.pread(fd, len(ending), (244318208-33)*512) == ending
            assert os.pread(fd, len(table), table_lba*512) == table
            assert os.pread(fd, 4096, 4096*512) == active
            assert sha(os.pread(fd, 14876672, 65536*512)) == BUNDLE
            assert sha(os.pread(fd, 14876672, 98304*512)) == SPARE
        except BaseException:
            assert os.pwrite(fd, original, 256*512) == 40960
            os.fsync(fd)
            assert os.pread(fd, 40960, 256*512) == original
            atomic(runtime, original_runtime, 0o755)
            print('DRAM_BOOT_VOLTAGE_TRANSACTION_RESTORED_ORIGINAL', flush=True)
            raise
        for name, digest in mirrors.items():
            assert sha(Path(name).read_bytes()) == digest, name
        if a.restore:
            run('systemctl', 'enable', 'tzx-cpufreq.service')
        record = {'state': 'original_reboot_pending' if a.restore else '1260_before_training_reboot_pending',
                  'previous_boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  'toc0_sha256': sha(target), 'kernel_bundle_sha256': BUNDLE,
                  'rtc_runtime_sha256': sha(target_runtime), 'live_voltage_units_retired': retired,
                  'pmic_writes_from_linux': 0}
        atomic(Path('/var/lib/tzx/dram-boot-voltage.json'), json.dumps(record, indent=2).encode()+b'\n')
        os.sync()
        print('DRAM_BOOT_VOLTAGE_TRANSACTION_READBACK_PASS', json.dumps(record), flush=True)
        run('systemd-run', '--unit=tzx-dram-boot-voltage-'+('restore' if a.restore else 'activate')+'-reboot',
            '--on-active=3s', '/usr/bin/systemctl', 'reboot')
finally:
    os.close(fd)
