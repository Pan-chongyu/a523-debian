"""Check the recorded SRAM initializer and complete native boot independently."""
import json,os,subprocess,sys
from pathlib import Path

assert os.geteuid()==0 and sys.argv[1:] in ([],['--key-on'])
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
key_on=bool(sys.argv[1:])
request=json.loads((state/'boot-panel-trial-request.json').read_text())
assert request['previous_boot_id']!=boot
assert request['action']==('poweroff' if key_on else 'reboot')
subprocess.run(['python3','/home/debian/verify_boot_panel_native_stack.py']+sys.argv[1:],check=True,timeout=100)
receipt=json.loads((state/'boot-panel-stage.json').read_text())
assert receipt['boot_id']==boot and receipt['stage']=='0x100' and receipt['active_on_entry']
assert receipt['panel_id']=='0x936504' and int(receipt['panel_status'],16)&16
assert receipt['line_before']!=receipt['line_after']
assert 0<receipt['entered_counter_s']<1 and 0<receipt['lit_counter_s']<3
assert receipt['result']=='early-preview-released-before-native-input-and-display'
assert receipt['DSI_mux_divider_ownership']=='retained 150 MHz source for registered Linux CCF'
native=json.loads((state/'boot-latency-qualified.json').read_text())
assert native['boot_id']==boot and native['status']=='PASS'
installed=json.loads((state/'boot-panel-installed.json').read_text())
assert installed['toc0_sha256']==native['toc0_sha256']
assert installed['handoff_CCF_mux_preserved_revision']==1
if key_on:
    pmic=json.loads(subprocess.check_output(['python3',
        '/usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py'],text=True,timeout=20))
    assert pmic['boot_id']==boot and pmic['axp717']['0x85']=='0xc9'
    assert int(pmic['axp717']['0x20'],16)&1
    # Bit0 in REG21 is a key-off, bit1 is a software-off. Preserve that
    # distinction; both establish a real PMIC shutdown before key power-on.
    assert int(pmic['axp717']['0x21'],16) in (1,2)
    assert int(pmic['axp717']['0x27'],16)==8
else:pmic=None
record=dict(status='PASS',boot_id=boot,early_panel_success=True,
    normal_reboot_verified=not key_on,PMIC_key_on_verified=key_on,
    PMIC_previous_off_source=('software' if pmic and int(pmic['axp717']['0x21'],16)==2
        else 'physical-key' if pmic else None),
    PMIC_software_off_verified=bool(pmic and int(pmic['axp717']['0x21'],16)==2),
    SRAM_receipt=receipt,native_stack=native,PMIC=pmic,
    user_first_light_confirmation='pending',user_desktop_touch_confirmation='pending',
    physical_zero_latency_achieved=False,preview_to_native_blank_interval='pending user observation')
if key_on:record['normal_reboot_proof']=request['prior_early_panel_proof']
target=state/('boot-panel-key-on-qualified.json' if key_on else 'boot-panel-reboot-qualified.json')
target.write_text(json.dumps(record,indent=2)+'\n')
(state/'boot-panel-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
os.sync()
print('SRAM_PANEL_AND_COMPLETE_NATIVE_BOOT_QUALIFIED',json.dumps(dict(boot_id=boot,
    first_backlight_counter_s=receipt['lit_counter_s'],key_on=key_on)),flush=True)
