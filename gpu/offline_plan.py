#!/usr/bin/env python3
"""Simulate installation with add-on packages absent, without changing dpkg state. MIT."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from fetch_packages import verify
from install import reject_package_replacements


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--debs', type=Path, required=True)
    args = p.parse_args()
    manifest = json.loads(Path(__file__).with_name('packages.json').read_text())
    binaries = verify(args.debs, manifest)
    names = {item['package'] for item in manifest['files']}
    status_path = Path('/var/lib/dpkg/status')
    before = status_path.read_bytes()
    paragraphs, removed = [], []
    for paragraph in before.decode().split('\n\n'):
        match = re.search(r'^Package: (.+)$', paragraph, re.M)
        if match and match.group(1) in names:
            removed.append(match.group(1))
        elif paragraph.strip():
            paragraphs.append(paragraph)
    with tempfile.TemporaryDirectory(prefix='tzx-gpu-offline-plan-') as temporary:
        status = Path(temporary) / 'status'
        status.write_text('\n\n'.join(paragraphs) + '\n\n')
        command = ['apt-get', '-o', 'Dir::State::status=' + str(status), '--simulate',
                   '--no-download', '--no-upgrade', '--no-install-recommends', 'install',
                   *(str(path) for path in binaries)]
        plan = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT,
                                       env=dict(os.environ, LC_ALL='C'), timeout=120)
    reject_package_replacements(plan)
    installed = {match.group(1).split(':')[0] for match in re.finditer(r'^Inst (\S+)', plan, re.M)}
    if installed != names:
        raise RuntimeError('Offline dependency closure differs: ' + str(installed ^ names) + '\n' + plan)
    if status_path.read_bytes() != before:
        raise RuntimeError('Live dpkg status changed during the simulation')
    print(json.dumps({'status': 'PASS', 'test': 'offline dependency simulation only',
        'packages_planned': sorted(installed), 'packages_hidden_from_simulated_status': sorted(removed),
        'upgrades': 0, 'removals': 0, 'live_dpkg_status_unchanged': True,
        'live_status_sha256': hashlib.sha256(before).hexdigest(),
        'physical_fresh_install_tested': False}, indent=2))


if __name__ == '__main__':
    main()
