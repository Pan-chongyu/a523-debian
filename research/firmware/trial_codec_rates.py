"""Temporary rate module; always put the installed codec and desktop audio back."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
installed = Path('/lib/modules/7.3.3-tzx-a523-accel1/extra/tzx_codec_driver.ko')
candidate = Path('/home/debian/tzx_codec_rates.ko')
assert hashlib.sha256(installed.read_bytes()).hexdigest() == '3ae8027ef29b6e3f919affe45b34fbb9be44ed28a5399d6532e2adc140b50acd'
assert hashlib.sha256(candidate.read_bytes()).hexdigest() == '013bcbe659aba5cae4d747c18fdce0c38b81ba782527bccab528f1de8132bf2d'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True).strip()
prefix = ['sudo', '-u', 'debian', 'env', 'XDG_RUNTIME_DIR=/run/user/1000', 'systemctl', '--user']


def run(*command, timeout=35):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


for unit in ('pulseaudio.service', 'pulseaudio.socket'):
    assert run(*prefix, 'is-enabled', unit).strip() == 'enabled'
    assert run(*prefix, 'is-active', unit).strip() == 'active'
run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
run(*prefix, 'mask', '--runtime', 'pulseaudio.service', 'pulseaudio.socket')
try:
    run(*prefix, 'stop', 'pulseaudio.service', 'pulseaudio.socket')
    run('systemctl', 'stop', 'tzx-audio.service')
    Path('/sys/bus/platform/drivers/tzx-a523-codec/unbind').write_text('7110000.audio-codec')
    run('rmmod', 'tzx_codec_driver')
    assert not Path('/sys/module/tzx_codec_driver').exists()
    run('insmod', str(candidate))
    assert Path('/sys/bus/platform/devices/7110000.audio-codec/pcm_counters').is_file()
    result = subprocess.run(['python3', '-u', '/home/debian/verify_codec_rates.py', '--label', 'manual'],
                            check=True, timeout=140)
finally:
    if Path('/sys/module/tzx_codec_driver').exists():
        if Path('/sys/bus/platform/drivers/tzx-a523-codec/7110000.audio-codec').exists():
            Path('/sys/bus/platform/drivers/tzx-a523-codec/unbind').write_text('7110000.audio-codec')
        run('rmmod', 'tzx_codec_driver')
    run('systemctl', 'start', 'tzx-audio.service')
    run(*prefix, 'unmask', '--runtime', 'pulseaudio.service', 'pulseaudio.socket')
    run(*prefix, 'start', 'pulseaudio.socket', 'pulseaudio.service')
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
run('python3', '/usr/local/lib/tzx-cpu-cooling/runtime.py', 'verify')
print('CODEC_RATE_TRIAL_ORIGINAL_MODULE_AND_DESKTOP_AUDIO_RESTORED', flush=True)
