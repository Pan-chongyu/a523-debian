"""Enable temporary boot instruction cache, restoring it on every exit."""
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
OLD = '319cdcc46804ce7136b5f00479dd6c320bc561340ea285655293de3665ab179e'
BUNDLE = 'c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'
FALLBACK = '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'
BACKUP = Path('/root/tzx-recovery/boot-icache-v1')
STATE = Path('/var/lib/tzx/boot-icache-installed.json')
FOLDER = Path('/home/debian/boot-icache')
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
assert manifest['ARM_emulation_verified'] and manifest['instruction_cache_only']
assert manifest['MMU_data_cache_voltage_clocks_unchanged']
assert manifest['original_control_restored_before_handoff']
assert manifest['SRAM_receipt_address'] == '0x2dfc0'
assert len(manifest['emulation']) == 7 and all(t['status'] == 'PASS' for t in manifest['emulation'])
assert manifest['previous_toc0_sha256'] == OLD and len(manifest['patches']) == 3
assert manifest['firmware_bytes'] == 36672 and manifest['hook_bytes'] == 316
assert sha(candidate[0xf80:0xf80+36672]) == manifest['firmware_sha256']
assert candidate[0xf80+36672:] == bytes(len(candidate)-0xf80-36672)
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
        begin = 0xf80
        expected = bytearray(original[begin:begin+35736])
        for item in manifest['patches']:
            offset = item['address']-0x44000
            assert struct.unpack_from('<I', expected, offset)[0] == item['old']
            struct.pack_into('<I', expected, offset, item['new'])
        assert candidate[begin:begin+35736] == expected
        for a, b in ((0, 0x0c), (0x10, 0x58), (0x5c, 0xc80)):
            assert original[a:b] == candidate[a:b], (a, b)
        assert original[0xc80:0xc80+445] == candidate[0xc80:0xc80+445]
        assert original[0xc80+477:0xf80-256] == candidate[0xc80+477:0xf80-256]
        assert not run('systemctl', '--failed', '--no-legend', '--plain').strip()
        previous = json.loads(Path('/var/lib/tzx/boot-fast-installed.json').read_text())
        assert previous['toc0_sha256'] == OLD and previous.get('verified_boot_id')
        proof = Path('/var/lib/tzx/boot-latency-qualified.json').read_bytes()
        assert json.loads(proof)['boot_id'] == previous['verified_boot_id'] and json.loads(proof)['status'] == 'PASS'
        assert json.loads(proof)['toc0_sha256'] == OLD
        for component in ('tzx-cpu-full', 'tzx-gpu-devfreq', 'tzx-emmc-hs'):
            component_manifest = json.loads((Path('/usr/local/lib')/component/'manifest.json').read_text())
            for name, digest in component_manifest['files'].items():
                assert sha(Path(name).read_bytes()) == digest, name
        for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs'):
            live = json.loads(Path('/run/tzx-'+name+'.json').read_text())
            assert live['boot_id'] == BOOT and live['state'] == 'active'
        pins = {name: previous['files'][name]['installed_sha256'] for name in (
            '/usr/local/lib/tzx-dram-gpu/runtime.py',
            '/usr/local/lib/tzx-rtc-context/runtime.py',
            '/usr/local/lib/tzx-pmic-poweroff/runtime.py')}
        originals = {name: Path(name).read_bytes() for name in pins}
        replacements = {}
        for name, data in originals.items():
            assert sha(data) == pins[name], name
            needle = ("'"+OLD+"')").encode()
            assert data.count(needle) == 1
            replacements[name] = data.replace(needle, ("'"+OLD+"', '"+pin+"')").encode())
            compile(replacements[name], name, 'exec')
        name = '/var/lib/tzx/pmic-poweroff-installed.json'
        originals[name] = Path(name).read_bytes()
        value = json.loads(originals[name])
        assert value['files']['usr/local/lib/tzx-pmic-poweroff/runtime.py'] == pins['/usr/local/lib/tzx-pmic-poweroff/runtime.py']
        value['files']['usr/local/lib/tzx-pmic-poweroff/runtime.py'] = sha(replacements['/usr/local/lib/tzx-pmic-poweroff/runtime.py'])
        value['accepted_toc0_sha256'].append(pin)
        value['boot_icache_update_boot_id'] = BOOT
        replacements[name] = (json.dumps(value, indent=2)+'\n').encode()
        BACKUP.mkdir(parents=True)
        atomic(BACKUP/'original.toc0', original)
        atomic(BACKUP/'install_boot_icache.py', Path(__file__).read_bytes())
        atomic(BACKUP/'fast-pins-qualified.json', proof)
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
            record(STATE, dict(state='boot-icache-installed-pending-reboot', installed_boot_id=BOOT,
                toc0_sha256=pin, original_toc0_sha256=OLD, files=files, backup=str(BACKUP),
                kernel_bundle_sha256=BUNDLE, fallback_bundle_sha256=FALLBACK,
                raw_invariants={k:sha(v) for k,v in invariant.items()},
                ARM_emulation=manifest['emulation'], runtime_accepts_exact_previous_and_candidate=True, CPU4_7_MHz=480, voltages_unchanged=True))
            os.sync()
        except BaseException:
            assert os.pwrite(fd, original, 256*512) == 40960
            os.fsync(fd)
            assert os.pread(fd, 40960, 256*512) == original
            for name, data in originals.items():
                atomic(Path(name), data, files[name]['mode'])
            raise
        print('BOOT_ICACHE_INSTALLED_AND_READBACK_VERIFIED', pin, flush=True)
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
            print('BOOT_ICACHE_RAW_BOOT_AND_RUNTIME_INVARIANTS_PASS', pin, flush=True)
finally:
    os.close(fd)
