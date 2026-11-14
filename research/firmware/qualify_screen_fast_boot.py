"""Check real display/touch overlap and the retained performance stack after reboot."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

assert os.geteuid() == 0
state = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert sys.argv[1:] in ([], ['--key-on'])
key_on = sys.argv[1:] == ['--key-on']
request = json.loads((state/('screen-fast-key-on-request.json' if key_on else 'screen-fast-reboot-request.json')).read_text())
assert boot != request['previous_boot_id']
units = ('tzx-touch', 'tzx-touch-input-ready', 'tzx-display', 'tzx-thermal', 'tzx-video', 'tzx-gpu',
         'lightdm', 'tzx-screen-health', 'tzx-dram-gpu-health', 'tzx-cpu-dvfs', 'tzx-gpu-performance', 'tzx-emmc-hs')
for attempt in range(140):
    result = subprocess.run(['systemctl','is-active',*units],capture_output=True,text=True,timeout=10)
    if result.stdout.split() == ['active']*len(units):
        break
    if attempt % 20 == 0:
        print('WAITING_FOR_FAST_SCREEN_BOOT_HEALTH',dict(zip(units,result.stdout.split())),flush=True)
    time.sleep(.5)
else:
    raise RuntimeError('Fast screen services did not finish: '+result.stdout)
subprocess.run(['python3','/home/debian/install_screen_fast_boot.py','verify'],check=True,timeout=40)
subprocess.run(['python3','/home/debian/verify_boot_latency.py'] + (['--key-on'] if key_on else []),check=True,timeout=85)
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
assert not (state/'screen-boot-pending.json').exists() and not (state/'dram-gpu-boot-pending.json').exists()
rail = json.loads(Path('/run/tzx-touch-rail-ready.json').read_text())
ready = json.loads(Path('/run/tzx-touch-input-ready.json').read_text())
assert rail['boot_id'] == ready['boot_id'] == boot
stats = Path('/sys/bus/i2c/devices/1-0040/stats').read_text().strip()
assert 'read_errors=0' in stats
def at(name, prop):
    return int(subprocess.check_output(['systemctl','show',name,'-p',prop,'--value'],text=True))/1000000
display_start = at('tzx-display','ExecMainStartTimestampMonotonic')
display_end = at('tzx-display','ActiveEnterTimestampMonotonic')
assert rail['monotonic_s'] < display_start < ready['monotonic_s'], (rail,display_start,ready)
assert ready['monotonic_s'] < at('lightdm','ExecMainStartTimestampMonotonic')
assert at('tzx-thermal','ActiveEnterTimestampMonotonic') <= at('tzx-video','ExecMainStartTimestampMonotonic')
log = subprocess.check_output(['dmesg'],text=True)
assert "Don't multithread overlaying and probing" not in log
unexpected = [line for line in log.splitlines()
    if re.search(r'\bWARNING:|\bBUG:|\bOops:|\bSError\b', line)
    and not re.search(r'OF: overlay: WARNING: memory leak will occur if overlay removed, property: '
        r'/soc/gpu@1800000/(operating-points-v2|mali-supply|assigned-clocks|assigned-clock-rates|status)$', line)]
assert not unexpected, unexpected
fb = re.search(r'\[\s*([0-9.]+)\] Console: switching to colour frame buffer',log)
assert fb
current = json.loads((state/'boot-latency-qualified.json').read_text())
assert current['status']=='PASS' and current['boot_id']==boot
record = dict(status='PASS',boot_id=boot,normal_reboot_verified=True,
    previous_boot_id=request['previous_boot_id'],rail_ready=rail,input_ready=ready,
    display_start_s=display_start,display_ready_s=display_end,first_fbcon_kernel_s=float(fb[1]),
    lightdm_started_s=at('lightdm','ExecMainStartTimestampMonotonic'),
    prior_key_on_first_fbcon_kernel_s=18.682668,
    first_fbcon_saved_s=round(18.682668-float(fb[1]),6),
    display_started_during_firmware_upload=True,desktop_waited_for_full_input=True,
    input_stats=stats,SID_overlay_order_verified=True,raw_boot_changed=False,
    unchanged_native_stack=current,visual_confirmation='pending',poweroff_key_on_verified=key_on,
    verification_method='PMIC-off-physical-key-on' if key_on else 'normal-reboot',
    complete_removal_of_power_tested=False)
if key_on:
    pmic = json.loads(subprocess.check_output(['python3',
        '/usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py'],text=True,timeout=20))
    assert pmic['boot_id'] == boot and pmic['axp323_id'] == '0x49'
    assert int(pmic['axp717']['0x20'],16)&1 and int(pmic['axp717']['0x21'],16)&2
    assert not int(pmic['axp717']['0x21'],16)&0xf8
    assert pmic['axp717']['0x85']=='0xc9' and int(pmic['axp717']['0x27'],16)==8
    record.update(pmic_status=pmic,normal_reboot_proof=request['normal_screen_proof'])
    (state/'screen-fast-key-on-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
(state/'screen-fast-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
installed=json.loads((state/'screen-fast-installed.json').read_text())
installed.update(state='actual-normal-and-PMIC-key-on-verified' if key_on else 'actual-normal-reboot-and-native-stack-verified',
    verified_boot_id=boot,normal_reboot_verified=True,first_fbcon_kernel_s=float(fb[1]),
    poweroff_key_on_verified=key_on)
(state/'screen-fast-installed.json').write_text(json.dumps(installed,indent=2)+'\n')
os.sync()
print('SCREEN_EARLY_FIRST_FRAME_AND_COMPLETE_LANDSCAPE_STACK_PASS',json.dumps({
    k:v for k,v in record.items() if k!='unchanged_native_stack'}),flush=True)
