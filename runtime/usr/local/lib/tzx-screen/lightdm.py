#!/usr/bin/python3
"""Use the landscape Xorg configuration for this qualified display revision."""
import os
from pathlib import Path
import subprocess

revision = Path('/sys/module/tzx_display/parameters/screen_revision')
if (revision.exists() and revision.read_text().strip() == 'screen-functions-5-poweron'
        and Path('/sys/module/panfrost/parameters/tzx_dma32').exists()
        and subprocess.run(['systemctl', 'is-active', '--quiet', 'tzx-gpu.service']).returncode == 0):
    os.execv('/usr/sbin/lightdm', ['/usr/sbin/lightdm', '--config=/usr/local/lib/tzx-screen/lightdm.conf'])
os.execv('/usr/bin/python3', ['/usr/bin/python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'lightdm'])
