#!/usr/bin/env python3
"""Install or remove the board-specific GPU API add-on. MIT."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile

from fetch_packages import verify as verify_packages

HERE = Path(__file__).resolve().parent
VERSION = '0.3.0'
MESA = '25.0.7-2+deb13u1'
STATE = Path('/var/lib/tzx/gpu-api-installed.json')
PREFIX = Path('/usr/local/lib/tzx-gpu-api')
PROGRAMS = ('opencl_check.py', 'opencl_extended.py', 'webgl_check.py', 'gles_compute.py',
            'gles_pixels.py', 'ram_check.py', 'soak.py', 'info.py', 'spirv_check.py', 'health.py')
PACKAGES = ('mesa-opencl-icd=' + MESA, 'clinfo=3.0.25.02.14-1',
            'ocl-icd-opencl-dev=2.3.3-1', 'vulkan-tools=1.4.304.0+dfsg1-1')
OPENCL = b'''#!/bin/sh
# MIT; select the real Panfrost GPU without exposing CPU ICDs.
if [ "$#" -eq 0 ]; then set -- clinfo; fi
exec /usr/bin/env RUSTICL_ENABLE=panfrost OCL_ICD_VENDORS=/etc/OpenCL/vendors/rusticl.icd "$@"
'''
CHECK = b'''#!/bin/sh
# MIT
if [ "$#" -eq 0 ]; then set -- info; fi
case "$1" in
  info) shift; exec python3 /usr/local/lib/tzx-gpu-api/info.py "$@" ;;
  opencl) shift; exec tzx-opencl python3 /usr/local/lib/tzx-gpu-api/opencl_check.py "$@" ;;
  opencl3) shift; exec tzx-opencl python3 /usr/local/lib/tzx-gpu-api/opencl_extended.py "$@" ;;
  spirv) shift; exec tzx-opencl python3 /usr/local/lib/tzx-gpu-api/spirv_check.py "$@" ;;
  webgl) shift; exec python3 /usr/local/lib/tzx-gpu-api/webgl_check.py "$@" ;;
  soak) shift; exec python3 /usr/local/lib/tzx-gpu-api/soak.py "$@" ;;
  *) echo 'Usage: tzx-gpu-check [info|opencl|opencl3|spirv|webgl --output FILE|soak --duration 3600 --output NEW_DIRECTORY]' >&2; exit 2 ;;
esac
'''
PROFILE = b'# MIT; enable the Mali-G57 Rusticl device for login shells and X11 applications.\nexport RUSTICL_ENABLE=panfrost\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def output(command):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def validate_board(require_gpu=True):
    if platform.system() != 'Linux' or platform.machine() != 'aarch64':
        raise RuntimeError('This add-on must run on the ARM64 tablet, not on the host PC')
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if b'tzx,p30a523\0' not in Path('/proc/device-tree/compatible').read_bytes():
        raise RuntimeError('Unsupported device tree; expected the adapted TZX P30 A523 board')
    if Path('/sys/class/block/mmcblk0/size').read_text().strip() != '244318208':
        raise RuntimeError('Unsupported eMMC capacity')
    if not require_gpu:
        return  # Rollback must remain possible after a GPU guard has stopped the driver.
    if Path('/sys/module/panfrost/parameters/tzx_dma32').read_text().strip() != 'Y':
        raise RuntimeError('Qualified native Panfrost DMA32 configuration is required')
    subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-gpu-performance'], check=True)


def reject_package_replacements(plan):
    for line in plan.splitlines():
        if line.startswith('Remv ') or re.match(r'^Inst \S+ \[', line):
            raise RuntimeError('Refusing package removal/upgrade: ' + line)


def files_to_install():
    files = {PREFIX / name: ((HERE / name).read_bytes(), 0o644) for name in PROGRAMS}
    files.update({
        Path('/usr/local/bin/tzx-opencl'): (OPENCL, 0o755),
        Path('/usr/local/bin/tzx-gpu-check'): (CHECK, 0o755),
        Path('/etc/profile.d/70-tzx-opencl.sh'): (PROFILE, 0o644),
        Path('/etc/X11/Xsession.d/25tzx-opencl'): (PROFILE, 0o644),
        Path('/etc/environment.d/70-tzx-opencl.conf'): (b'RUSTICL_ENABLE=panfrost\n', 0o644),
        Path('/etc/systemd/system/tzx-gpu-api-health.service'): ((HERE / 'tzx-gpu-api-health.service').read_bytes(), 0o644),
    })
    return files


def rollback():
    if not STATE.exists():
        raise RuntimeError('No installation record; no files were removed')
    state = json.loads(STATE.read_text())
    allowed = set(files_to_install())
    for name, digest in state['files'].items():
        path = Path(name)
        if path not in allowed:
            raise RuntimeError('Unexpected path in installation record: ' + name)
        if path.exists() and sha(path.read_bytes()) != digest:
            raise RuntimeError('Locally modified file preserved; resolve before rollback: ' + name)
    if '/etc/systemd/system/tzx-gpu-api-health.service' in state['files']:
        subprocess.run(['systemctl', 'disable', '--now', 'tzx-gpu-api-health'], check=True)
    for name in state['files']:
        Path(name).unlink(missing_ok=True)
    STATE.unlink()
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('GPU API launchers/configuration removed. Debian packages retained; log out/in to clear session environment.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rollback', action='store_true')
    p.add_argument('--skip-apt', action='store_true', help='require the exact packages to be already installed')
    p.add_argument('--offline', type=Path, help='directory containing all SHA256-verified .deb files')
    p.add_argument('--user', default='debian', help='unprivileged account for the GPU acceptance test')
    args = p.parse_args()
    if args.skip_apt and args.offline:
        p.error('--skip-apt and --offline are mutually exclusive')
    validate_board(require_gpu=not args.rollback)
    if args.rollback:
        rollback()
        return
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', args.user) or args.user == 'root':
        p.error('choose a non-root local account')
    # One Mesa version across GL/EGL/OpenCL, no partial driver upgrades.
    for package in ('libegl-mesa0', 'libgbm1', 'libgl1-mesa-dri', 'libglx-mesa0', 'mesa-libgallium'):
        if output(['dpkg-query', '-W', '-f=${Version}', package]) != MESA:
            raise RuntimeError(f'{package} differs from qualified Mesa {MESA}; no changes made')
    files = files_to_install()
    previous = json.loads(STATE.read_text()) if STATE.exists() else {'files': {}}
    for path, (data, _) in files.items():
        if path.is_symlink():
            raise RuntimeError('Refusing symlink destination: ' + str(path))
        if path.exists() and sha(path.read_bytes()) != previous['files'].get(str(path)):
            raise RuntimeError('Refusing to overwrite an unowned or modified file: ' + str(path))
    # Validate sources and destinations before invoking the package manager.
    if not args.skip_apt:
        command = ['apt-get', '-y', '--no-upgrade', '--no-install-recommends', 'install', *PACKAGES]
        if args.offline:
            manifest = json.loads((HERE / 'packages.json').read_text())
            local_packages = verify_packages(args.offline, manifest)
            command = ['apt-get', '-y', '--no-download', '--no-upgrade', '--no-install-recommends',
                       'install', *(str(path) for path in local_packages)]
        environment = dict(os.environ, LC_ALL='C', DEBIAN_FRONTEND='noninteractive')
        plan = subprocess.check_output([command[0], '--simulate', *command[1:]], env=environment, text=True)
        reject_package_replacements(plan)
        subprocess.run(command, env=environment, check=True)
    for spec in PACKAGES:
        package, version = spec.split('=', 1)
        if output(['dpkg-query', '-W', '-f=${Version}', package]) != version:
            raise RuntimeError('Required exact package is missing: ' + spec)
    # Acceptance precedes activation. The command fails if only a CPU ICD is present.
    reports = {}
    for name in ('opencl_check.py', 'opencl_extended.py', 'spirv_check.py'):
        acceptance = subprocess.check_output(['runuser', '-u', args.user, '--', 'python3',
                                              str(HERE / name)], text=True, timeout=90)
        report = json.loads(acceptance)
        if report.get('status') != 'PASS' or report.get('cpu_fallback') is not False or report.get('device_type') != 4:
            raise RuntimeError('Native GPU OpenCL acceptance failed: ' + name)
        reports[name] = report
    originals = {path: (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None for path in files}
    original_state = STATE.read_bytes() if STATE.exists() else None
    was_enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', 'tzx-gpu-api-health'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    was_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-gpu-api-health'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    try:
        for path, (data, mode) in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
                temporary = Path(f.name)
                f.write(data)
            temporary.chmod(mode)
            temporary.replace(path)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        record = {'version': VERSION, 'installed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                  'kernel': platform.release(), 'mesa': MESA, 'acceptance': reports,
                  'files': {str(path): sha(data) for path, (data, _) in files.items()}}
        STATE.write_text(json.dumps(record, indent=2) + '\n')
        STATE.chmod(0o644)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', 'tzx-gpu-api-health'], check=True)
        subprocess.run(['systemctl', 'restart', 'tzx-gpu-api-health'], check=True)
    except BaseException:
        subprocess.run(['systemctl', 'stop', 'tzx-gpu-api-health'], check=False)
        if not was_enabled:
            subprocess.run(['systemctl', 'disable', 'tzx-gpu-api-health'], check=False)
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original[0]); path.chmod(original[1])
        if original_state is None:
            STATE.unlink(missing_ok=True)
        else:
            STATE.write_bytes(original_state)
        subprocess.run(['systemctl', 'daemon-reload'], check=False)
        if was_active:
            subprocess.run(['systemctl', 'start', 'tzx-gpu-api-health'], check=False)
        raise
    print('GPU API add-on installed; tzx-gpu-check opencl works now. Log out/in or reboot for application-wide OpenCL discovery.')
    print('Vulkan hardware support is unavailable for Mali-G57 in this open driver; no software fallback is installed.')


if __name__ == '__main__':
    main()
