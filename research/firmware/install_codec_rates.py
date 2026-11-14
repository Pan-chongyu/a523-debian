"""Reversible two-file codec-rate upgrade on the exact trained #5 board."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('operation', choices=('install', 'verify-boot', 'restore'))
args = parser.parse_args()
assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
BACKUP = Path('/root/tzx-recovery/codec-rates')
STATE = Path('/var/lib/tzx/codec-rates-installed.json')
MODULE = 'lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_codec_driver.ko'
LIST = 'usr/local/lib/tzx-accel-audio/MODULES.sha256'
OLD = '3ae8027ef29b6e3f919affe45b34fbb9be44ed28a5399d6532e2adc140b50acd'
NEW = '013bcbe659aba5cae4d747c18fdce0c38b81ba782527bccab528f1de8132bf2d'
sha = lambda data: hashlib.sha256(data).hexdigest()
prefix = ['sudo', '-u', 'debian', 'env', 'XDG_RUNTIME_DIR=/run/user/1000', 'systemctl', '--user']


def run(*command, timeout=40):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


def atomic(path, data, mode=0o600):
    assert not path.is_symlink(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.rate-new')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fchown(stream.fileno(), 0, 0)
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
    assert path.read_bytes() == data


def health():
    print(run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify'), flush=True)
    for service in ('tzx-audio', 'tzx-gpu', 'lightdm', 'tzx-pmic-poweroff'):
        assert run('systemctl', 'is-active', service+'.service').strip() == 'active'
    assert run('systemctl', '--failed', '--no-legend').strip() == ''
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096


def replace(files):
    for unit in ('pulseaudio.service', 'pulseaudio.socket'):
        assert run(*prefix, 'is-enabled', unit).strip() == 'enabled'
    run(*prefix, 'mask', '--runtime', 'pulseaudio.service', 'pulseaudio.socket')
    try:
        run(*prefix, 'stop', 'pulseaudio.service', 'pulseaudio.socket')
        run('systemctl', 'stop', 'tzx-audio.service')
        Path('/sys/bus/platform/drivers/tzx-a523-codec/unbind').write_text('7110000.audio-codec')
        run('rmmod', 'tzx_codec_driver')
        for name, data in files.items():
            atomic(Path('/')/name, data, 0o644)
        run('depmod', '-a', os.uname().release)
        run('systemctl', 'start', 'tzx-audio.service')
    finally:
        run(*prefix, 'unmask', '--runtime', 'pulseaudio.service', 'pulseaudio.socket')
        run(*prefix, 'start', 'pulseaudio.socket', 'pulseaudio.service')


health()
if args.operation == 'install':
    assert sha((Path('/')/MODULE).read_bytes()) == OLD
    assert not BACKUP.exists() and not STATE.exists()
    proof = json.loads(Path('/var/lib/tzx/codec-rates-manual.json').read_text())
    assert proof['boot_id'] == BOOT and proof['result'] == 'PASS' and len(proof['tests']) == 16
    props = run('systemctl', 'show', 'tzx-codec-rate-trial.service', '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus')
    assert all(value in props for value in ('ActiveState=inactive', 'Result=success', 'ExecMainStatus=0'))
    package = Path('/home/debian/audio-rates-runtime.tar.gz').read_bytes()
    assert sha(package) == 'd56070e20bd976e4b7bce13253757e15ad1321bdf4ff0c0758c1c1db78e5ae30'
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        members = archive.getmembers()
        assert len(members) == 3 and len({m.name for m in members}) == 3
        assert all(m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts for m in members)
        manifest = json.load(archive.extractfile('FILES.json'))
        assert set(manifest) == {MODULE, LIST} and {m.name for m in members} == set(manifest) | {'FILES.json'}
        files = {name: archive.extractfile(name).read() for name in manifest}
    for name, digest in manifest.items():
        assert sha(files[name]) == digest
    assert manifest[MODULE] == NEW
    previous = {name: (Path('/')/name).read_bytes() for name in manifest}
    assert files[LIST] == previous[LIST].replace(OLD.encode(), NEW.encode())
    before = {name: sha(data) for name, data in previous.items()}
    for name, data in previous.items():
        atomic(BACKUP/'files'/name, data)
    atomic(BACKUP/'before.json', json.dumps(before, indent=2).encode()+b'\n')
    atomic(BACKUP/'files.json', json.dumps(manifest, indent=2).encode()+b'\n')
    atomic(BACKUP/'installer.py', Path(__file__).read_bytes())
    atomic(BACKUP/'runtime-package.tar.gz', package)
    try:
        replace(files)
        health()
    except BaseException:
        # Do not force module removal. A failed normal restore is reported.
        replace(previous)
        raise
    state = {'state': 'manual_matrix_passed_installed_pending_reboot', 'boot_id': BOOT,
             'files': manifest, 'manual_matrix_tests': 16, 'new_module_sha256': NEW,
             'rate_family': '48k only, fixed 24.576 MHz', 'S16_only': True}
    atomic(STATE, json.dumps(state, indent=2).encode()+b'\n')
    os.sync()
    print('CODEC_RATE_UPGRADE_INSTALLED_ORIGINAL_FILES_SAVED_PENDING_REBOOT', flush=True)
else:
    state = json.loads(STATE.read_text())
    for name, digest in state['files'].items():
        assert sha((Path('/')/name).read_bytes()) == digest, name
    if args.operation == 'restore':
        before = json.loads((BACKUP/'before.json').read_text())
        previous = {name: (BACKUP/'files'/name).read_bytes() for name in before}
        assert all(sha(previous[name]) == before[name] for name in previous)
        replace(previous)
        state.update(state='restored_original_48k_codec', restored_boot_id=BOOT)
    else:
        assert state['boot_id'] != BOOT
        log = run('journalctl', '-b', '-u', 'tzx-audio.service', '-o', 'cat', '--no-pager')
        assert 'TZX_AUDIO_READY' in log and NEW in (Path('/')/LIST).read_text()
        assert run('systemctl', 'is-enabled', 'tzx-pmic-poweroff.service').strip() == 'enabled'
        assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip() == 'Y'
        state.update(state='manual_matrix_and_actual_autostart_verified', verified_boot_id=BOOT,
                     poweroff_handler_autostart_verified=True)
    atomic(STATE, json.dumps(state, indent=2).encode()+b'\n')
    health()
    print('CODEC_RATE_'+args.operation.upper().replace('-', '_')+'_PASS', flush=True)
