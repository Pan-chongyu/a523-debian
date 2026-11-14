#!/usr/bin/env python3
"""Verify installed GPU APIs, desktop environment and guards after reboot. MIT."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def run(command, timeout=90):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo on the tablet')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    units = ('tzx-gpu-api-health', 'tzx-gpu-performance', 'tzx-cpu-dvfs', 'tzx-emmc-hs', 'tzx-display', 'lightdm')
    states = {unit: run(['systemctl', 'is-active', unit]) for unit in units}
    if any(value != 'active' for value in states.values()):
        raise RuntimeError(str(states))
    state = json.loads(Path('/var/lib/tzx/gpu-api-installed.json').read_text())
    if not all(hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha for name, sha in state['files'].items()):
        raise RuntimeError('Installed add-on hashes changed')
    taint = int(Path('/proc/sys/kernel/tainted').read_text())
    if taint != 4096:
        raise RuntimeError('Unexpected kernel taint: ' + str(taint))
    environment = None
    for process in Path('/proc').glob('[0-9]*'):
        try:
            if process.stat().st_uid == 1000 and (process / 'comm').read_text().strip() == 'xfce4-session':
                values = dict(p.split('=', 1) for p in (process / 'environ').read_bytes().decode().split('\0') if '=' in p)
                environment = {k: values.get(k) for k in ('DISPLAY', 'RUSTICL_ENABLE')}
                break
        except (OSError, ProcessLookupError):
            continue
    if environment != {'DISPLAY': ':0', 'RUSTICL_ENABLE': 'panfrost'}:
        raise RuntimeError('Desktop did not inherit OpenCL configuration: ' + str(environment))
    prefix = ['runuser', '-u', 'debian', '--']
    tests = {name: json.loads(run(prefix + ['tzx-gpu-check', name])) for name in ('opencl', 'opencl3', 'spirv')}
    if any(value['status'] != 'PASS' or value['cpu_fallback'] for value in tests.values()):
        raise RuntimeError('Native GPU acceptance failed')
    xprefix = prefix + ['env', 'DISPLAY=:0', 'XAUTHORITY=/home/debian/.Xauthority']
    glx = run(xprefix + ['glxinfo', '-B'])
    if 'direct rendering: Yes' not in glx or 'Mali-G57 (Panfrost)' not in glx:
        raise RuntimeError('Desktop graphics fell back')
    geometry = run(xprefix + ['xrandr', '--current'])
    if not re.search(r'current\s+1280\s+x\s+800\b', geometry):
        raise RuntimeError('Landscape desktop geometry changed: ' + geometry)
    errors = {name: int(Path('/sys/module/tzx_display/parameters', name).read_text())
              for name in ('screen_buffer_errors', 'screen_panel_errors')}
    mmc = Path('/sys/kernel/debug/mmc0/err_stats').read_text()
    if any(errors.values()) or any(int(line.rsplit(':', 1)[1]) for line in mmc.splitlines()):
        raise RuntimeError('Display/storage errors')
    kernel = run(['dmesg', '--color=never'])
    faults = [s for s in kernel.splitlines() if re.search(
        r'panfrost.*(?:fault|timeout|hang)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error|Out of memory', s, re.I)]
    failed = run(['systemctl', '--failed', '--no-legend', '--plain'])
    health = json.loads(Path('/run/tzx-gpu-api-health.json').read_text())
    if faults or failed or health['status'] != 'ACTIVE' or health['had_issue_this_session']:
        raise RuntimeError(str(dict(faults=faults, failed=failed, health=health)))
    print(json.dumps(dict(status='PASS', boot_id=boot, kernel_taint=taint,
        api=tests, services=states, installed_files_checked=len(state['files']),
        installed_hashes_match=True, desktop_environment=environment,
        landscape_geometry='1280x800', display_errors=errors, new_kernel_errors=0,
        mmc_errors=0, failed_units=[], health=health, glxinfo=glx), indent=2))


if __name__ == '__main__':
    main()
