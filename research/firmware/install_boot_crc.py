"""Install a CRC-only TOC0 patch with pinned code, readback and exact rollback."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import uuid
import zlib

assert os.geteuid() == 0 and len(sys.argv) == 3
operation, pin = sys.argv[1:]
assert operation in ('install', 'verify', 'restore') and re.fullmatch('[0-9a-f]{64}', pin)
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip() == '244318208'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
OLD = '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
BUNDLE = 'c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'
FALLBACK = '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'
BACKUP = Path('/root/tzx-recovery/boot-crc-v1')
STATE = Path('/var/lib/tzx/boot-crc-installed.json')
FOLDER = Path('/home/debian/boot-latency-loader')
sha = lambda b: hashlib.sha256(b).hexdigest()


def atomic(path, data, mode=0o600):
    assert not path.is_symlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.boot-crc-new')
    with tmp.open('wb') as f:
        f.write(data)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def record(path, value):
    atomic(path, (json.dumps(value, indent=2)+'\n').encode())


def run(*args, timeout=60):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)


def snapshot(fd):
    result = {
        'primary_gpt': os.pread(fd, 34*512, 0),
        'secondary_gpt': os.pread(fd, 33*512, (244318208-33)*512),
        'selection_header': os.pread(fd, 512, 4096*512),
        'active_bundle': os.pread(fd, 15008768, 98304*512),
        'fallback_bundle': os.pread(fd, 15008768, 65536*512),
    }
    header = bytearray(result['primary_gpt'][512:1024])
    assert header[:8] == b'EFI PART'
    assert str(uuid.UUID(bytes_le=bytes(header[56:72]))) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    crc = struct.unpack_from('<I', header, 16)[0]
    struct.pack_into('<I', header, 16, 0)
    assert zlib.crc32(header[:struct.unpack_from('<I', header, 12)[0]]) == crc
    assert sha(result['active_bundle']) == BUNDLE
    assert sha(result['fallback_bundle']) == FALLBACK
    assert result['selection_header'] == result['active_bundle'][:512]
    return result


candidate = (FOLDER/'loader.toc0').read_bytes()
manifest = json.loads((FOLDER/'loader.toc0.json').read_text())
assert len(candidate) == 40960 and sha(candidate) == manifest['image_sha256'] == pin
assert manifest['ARM_emulation_verified'] and manifest['mmc_DRAM_PMIC_CPU_BL31_kernel_unchanged']
assert all(t['cases'] == 128 and t['result'] == 'PASS' for t in manifest['emulation'])
assert manifest['original_toc0_sha256'] == OLD and manifest['old_instruction_changed'] == '0x44454'
assert manifest['firmware_bytes'] == 33344 and manifest['hook_bytes'] == 1068
assert sha(candidate[0xf80:0xf80+33344]) == manifest['firmware_sha256']
assert candidate[0xf80+33344:] == bytes(len(candidate)-0xf80-33344)
assert struct.unpack_from('<I', candidate, 0x64)[0] == 0x44000
cert = candidate[0xc80:0xf80]
n = int.from_bytes(cert[178:434], 'big')
e = int.from_bytes(cert[436:439], 'big')
assert e == 65537 and pow(int.from_bytes(cert[-256:], 'big'), e, n) == int.from_bytes(hashlib.sha256(cert[4:487]).digest(), 'big')
assert cert[445:477].hex() == manifest['firmware_sha256']
check = bytearray(candidate)
expected = struct.unpack_from('<I', check, 0x0c)[0]
struct.pack_into('<I', check, 0x0c, 0x5f0a6c39)
assert sum(struct.unpack('<10240I', check)) & 0xffffffff == expected

fd = os.open('/dev/mmcblk0', os.O_RDONLY if operation == 'verify' else os.O_RDWR | os.O_SYNC)
try:
    invariant = snapshot(fd)
    current = os.pread(fd, 40960, 256*512)
    if operation == 'install':
        assert not BACKUP.exists() and not STATE.exists() and sha(current) == OLD
        original = current
        # All trained DRAM, PIO, failure handling and hand-off instructions
        # remain byte-identical. Only the original CRC entry is redirected.
        begin = 0xf80
        patch = begin + 0x44454-0x44000
        assert struct.unpack_from('<I', original, patch)[0] == 0xe52de004
        assert struct.unpack_from('<I', candidate, patch)[0] == 0xea001e69
        assert original[begin:patch] == candidate[begin:patch]
        assert original[patch+4:begin+32064] == candidate[patch+4:begin+32064]
        for a, b in ((0, 0x0c), (0x10, 0x58), (0x5c, 0xc80)):
            assert original[a:b] == candidate[a:b], (a, b)
        assert original[0xc80:0xc80+445] == candidate[0xc80:0xc80+445]
        assert original[0xc80+477:0xf80-256] == candidate[0xc80+477:0xf80-256]
        assert not run('systemctl', '--failed', '--no-legend', '--plain').strip()
        pins = {
            '/usr/local/lib/tzx-dram-gpu/runtime.py': '9f302a905df3378e4ab85c2ae26f143afcd3b06a24c98e7bbfdd335afee67166',
            '/usr/local/lib/tzx-rtc-context/runtime.py': 'e1f7beb91db90ac8443dc46fff846754f4d34d7ca6d6dc63f8e5c481e39e2f44',
            '/usr/local/lib/tzx-pmic-poweroff/runtime.py': '88b2a59d25c1816d7fcd2d9d9b711fed22be768959041dde16c23b72e0c5c122',
        }
        originals = {name: Path(name).read_bytes() for name in pins}
        replacements = {}
        for name, data in originals.items():
            assert sha(data) == pins[name], name
            if 'rtc-context' in name:
                needle = ("'"+OLD+"')").encode()
                assert data.count(needle) == 1
                replacements[name] = data.replace(needle, ("'"+OLD+"', '"+pin+"')").encode())
            else:
                needle = ("== '"+OLD+"'").encode()
                assert data.count(needle) == 1
                replacements[name] = data.replace(needle, ("in ('"+OLD+"', '"+pin+"')").encode())
            compile(replacements[name], name, 'exec')
        name = '/var/lib/tzx/pmic-poweroff-installed.json'
        originals[name] = Path(name).read_bytes()
        value = json.loads(originals[name])
        assert value['files']['usr/local/lib/tzx-pmic-poweroff/runtime.py'] == pins['/usr/local/lib/tzx-pmic-poweroff/runtime.py']
        value['files']['usr/local/lib/tzx-pmic-poweroff/runtime.py'] = sha(replacements['/usr/local/lib/tzx-pmic-poweroff/runtime.py'])
        value['accepted_toc0_sha256'] = [OLD, pin]
        value['boot_crc_update_boot_id'] = BOOT
        replacements[name] = (json.dumps(value, indent=2)+'\n').encode()
        BACKUP.mkdir(parents=True)
        atomic(BACKUP/'original.toc0', original)
        atomic(BACKUP/'install_boot_crc.py', Path(__file__).read_bytes())
        atomic(BACKUP/'loader.toc0.json', (FOLDER/'loader.toc0.json').read_bytes())
        files = {}
        for name, data in originals.items():
            mode = Path(name).stat().st_mode & 0o777
            atomic(BACKUP/'files'/name.lstrip('/'), data, mode)
            files[name] = dict(original_sha256=sha(data), installed_sha256=sha(replacements[name]), mode=mode)
        record(BACKUP/'before.json', dict(boot_id=BOOT, files=files, raw_invariants={k:sha(v) for k,v in invariant.items()}))
        try:
            for name, data in replacements.items():
                atomic(Path(name), data, files[name]['mode'])
            os.sync()
            assert os.pwrite(fd, candidate, 256*512) == 40960
            os.fsync(fd)
            assert os.pread(fd, 40960, 256*512) == candidate
            assert snapshot(fd) == invariant
            print(run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard'), end='', flush=True)
            print(run('python3', '/usr/local/lib/tzx-pmic-poweroff/runtime.py', 'verify'), end='', flush=True)
            record(STATE, dict(state='CRC-only-installed-pending-reboot', installed_boot_id=BOOT,
                toc0_sha256=pin, original_toc0_sha256=OLD, files=files, backup=str(BACKUP),
                kernel_bundle_sha256=BUNDLE, fallback_bundle_sha256=FALLBACK,
                raw_invariants={k:sha(v) for k,v in invariant.items()},
                ARM_emulation=manifest['emulation'], runtime_accepts_exact_original_and_candidate=True))
            os.sync()
        except BaseException:
            assert os.pwrite(fd, original, 256*512) == 40960
            os.fsync(fd)
            assert os.pread(fd, 40960, 256*512) == original
            for name, data in originals.items():
                atomic(Path(name), data, files[name]['mode'])
            raise
        print('FAST_CRC_INSTALLED_AND_READBACK_VERIFIED', pin, flush=True)
    else:
        state = json.loads(STATE.read_text())
        assert state['toc0_sha256'] == pin and current == candidate
        assert state['raw_invariants'] == {k:sha(v) for k,v in invariant.items()}
        for name, item in state['files'].items():
            assert sha(Path(name).read_bytes()) == item['installed_sha256'], name
        if operation == 'restore':
            original = (BACKUP/'original.toc0').read_bytes()
            assert sha(original) == OLD
            assert os.pwrite(fd, original, 256*512) == 40960
            os.fsync(fd)
            assert os.pread(fd, 40960, 256*512) == original
            for name, item in state['files'].items():
                data = (BACKUP/'files'/name.lstrip('/')).read_bytes()
                assert sha(data) == item['original_sha256']
                atomic(Path(name), data, item['mode'])
            state.update(state='exact-original-loader-and-runtime-restored', restored_boot_id=BOOT)
            record(STATE, state)
            print('ORIGINAL_TRAINED_LOADER_AND_GUARDS_RESTORED', flush=True)
        else:
            print('FAST_CRC_RAW_BOOT_AND_RUNTIME_INVARIANTS_PASS', pin, flush=True)
finally:
    os.close(fd)
