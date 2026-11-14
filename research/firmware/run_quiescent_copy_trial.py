"""Bounded high-address CPU copy comparison with temporary peripheral removal."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--restore',action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state = Path('/run/tzx-quiescent-copy-state.json')
stop_order = ('lightdm','tzx-audio','tzx-display','tzx-touch','tzx-bluetooth','bluetooth','tzx-wifi')
start_order = ('tzx-wifi','bluetooth','tzx-bluetooth','tzx-touch','tzx-display','tzx-audio','lightdm')

def restore():
    if not state.exists():
        return
    saved = json.loads(state.read_text())
    assert saved['boot_id'] == boot and set(saved['active']).issubset(stop_order)
    for unit in start_order:
        if unit == 'tzx-audio' and unit in saved['active']:
            device = Path('/sys/bus/platform/devices/7110000.audio-codec')
            bind = Path('/sys/bus/platform/drivers/tzx-a523-codec/bind')
            if device.exists() and bind.exists() and not (device/'driver').exists():
                bind.write_text('7110000.audio-codec\n')
        if unit == 'lightdm':
            for audio_unit in ('pulseaudio.socket','pulseaudio.service'):
                if audio_unit in saved.get('user_audio',[]):
                    subprocess.run(['runuser','-u','debian','--','env',
                        'XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','start',audio_unit],
                        check=True,timeout=35)
        if unit in saved['active']:
            subprocess.run(['systemctl','start',unit],check=True,timeout=65)
    for unit in saved['active']:
        subprocess.run(['systemctl','is-active','--quiet',unit],check=True,timeout=10)
    state.unlink()
    print('QUIESCENT_COPY_PERIPHERALS_RESTORED',json.dumps(saved),flush=True)

if args.restore:
    restore()
    raise SystemExit(0)
assert not state.exists()
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
for module in ('panfrost','tzx_cpufreq_divider','tzx_sram_log'):
    assert not Path('/sys/module',module).exists(),module
binary = Path('/home/debian/library-copy-coherency-v7')
assert hashlib.sha256(binary.read_bytes()).hexdigest() == '86d65c7f7d431b459cad4cfa3224d32758a98c1849b78d4d3caea45652da9b9c'
active = [unit for unit in stop_order if subprocess.run(
    ['systemctl','is-active','--quiet',unit]).returncode == 0]
audio_command = ['runuser','-u','debian','--','env','XDG_RUNTIME_DIR=/run/user/1000',
                 'systemctl','--user']
user_audio = [unit for unit in ('pulseaudio.socket','pulseaudio.service')
              if subprocess.run([*audio_command,'is-active','--quiet',unit]).returncode == 0]
state.write_text(json.dumps({'boot_id':boot,'active':active,'user_audio':user_audio})+'\n')
try:
    for unit in stop_order:
        if unit in active:
            subprocess.run(['systemctl','stop',unit],check=True,timeout=65)
    if user_audio:
        subprocess.run([*audio_command,'stop',*user_audio],check=True,timeout=35)
    # The registered ASoC card itself holds module references, even with no
    # userspace PCM open. Release it through the previously verified unbind.
    unbind = Path('/sys/bus/platform/drivers/tzx-a523-codec/unbind')
    assert unbind.exists()
    unbind.write_text('7110000.audio-codec\n')
    subprocess.run(['modprobe','-r','tzx_codec_driver'],check=True,timeout=20)
    time.sleep(3)
    absent = ('tzx_display','tzx_codec_driver','aic8800_fdrv','aic8800_bsp','tzx_gsl3670')
    for module in absent:
        assert not Path('/sys/module',module).exists(),module
    assert not Path('/sys/class/bluetooth/hci0').exists()
    os.sync()
    Path('/proc/sys/vm/drop_caches').write_text('1\n')
    print('QUIESCENT_COPY_BEGIN',json.dumps({'boot_id':boot,'stopped_services':active,
        'unloaded_modules':absent,'duration_seconds':300,'usb_control_retained':True}),flush=True)
    result = subprocess.run([str(binary),'300','/home/debian/copy-quiescent-v7-high',
        '255','libc'],env=dict(os.environ,TZX_COPY_HIGH_TARGETS='1'),timeout=350)
    print('QUIESCENT_COPY_RESULT',result.returncode,flush=True)
finally:
    restore()
raise SystemExit(result.returncode)
