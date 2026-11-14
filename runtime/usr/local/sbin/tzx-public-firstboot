#!/usr/bin/python3
"""Generate per-install identities; the public image contains no usable keys."""
import os,secrets,subprocess
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx/public-firstboot-complete')
if state.exists():raise SystemExit(0)
subprocess.run(['ssh-keygen','-A'],check=True)
state.parent.mkdir(parents=True,exist_ok=True)
# NetworkManager creates its own secret_key; never seed it from the developer.
Path('/etc/machine-id').touch(exist_ok=True)
subprocess.run(['systemd-machine-id-setup'],check=True)
state.write_text('v0.1.0-20261114\n');state.chmod(0o600)
