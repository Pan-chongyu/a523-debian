"""Record the user's exact observations without overstating the power-off source."""
import json,os
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx')
normal='f383c729-73cb-441f-9d24-0151a3d3cfc6'
key='2b9d7927-8d4a-471e-9813-bfdd421b1579'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==key
user=dict(normal_reboot=dict(boot_id=normal,first_pattern_user_seconds_approx=4,
    observation='黑屏4s出现彩条，中途不黑屏了',visible_intermediate_blackout_reported=False),
    physical_key_on=dict(boot_id=key,first_pattern_user_seconds_approx=2,
    first_light_observation='按下去基本2s就亮屏了',desktop_touch_observation='桌面和触摸都正常',
    right_landscape_and_touch_confirmed=True),
    hardware_counter_starts_before_initializer=True,physical_zero_latency_claimed=False)
(state/'boot-panel-user-confirmed.json').write_text(json.dumps(user,ensure_ascii=False,indent=2)+'\n')
for name in ('boot-panel-reboot-qualified.json','boot-panel-key-on-qualified.json','boot-panel-qualified.json'):
    path=state/name;value=json.loads(path.read_text())
    assert value['status']=='PASS'
    if value['boot_id']==normal:
        value['user_first_light_confirmation']=user['normal_reboot']
        value['preview_to_native_blank_interval']='User reports no visible intermediate blackout'
    else:
        assert value['boot_id']==key
        value['user_first_light_confirmation']=user['physical_key_on']
        value['user_desktop_touch_confirmation']='right landscape and touch confirmed normal'
        prior=value['normal_reboot_proof']
        assert prior['boot_id']==normal and prior['status']=='PASS'
        prior['user_first_light_confirmation']=user['normal_reboot']
        prior['preview_to_native_blank_interval']='User reports no visible intermediate blackout'
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
final=state/'boot-panel-final-qualified.json';value=json.loads(final.read_text())
assert value['boot_id']==key and value['status']=='PASS'
value['PMIC_key_on_qualified']=json.loads((state/'boot-panel-key-on-qualified.json').read_text())
value['first_light_confirmation']=user
value['software_off_reason_confirmed_this_trial']=False
value['PMIC_off_source_evidence']='REG20=01 key-on, REG21=01 physical-key-off; do not label as REG21=02 software-off'
final.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
path=state/'boot-panel-installed.json';value=json.loads(path.read_text())
value.update(state='normal-reboot-and-physical-key-on-early-screen-and-native-desktop-verified',
    normal_verified_boot_id=normal,verified_boot_id=key,early_panel_qualification=True,
    user_first_light_confirmation='approximately 2 seconds from physical power key',
    user_right_landscape_and_touch_confirmed=True,physical_zero_latency_achieved=False,
    key_on_lit_counter_s=1.766584,full_stack_load_and_file_audit='PASS')
path.write_text(json.dumps(value,indent=2)+'\n')
os.sync()
print('EARLY_PANEL_USER_TWO_SECOND_KEY_ON_AND_RIGHT_LANDSCAPE_TOUCH_RECORDED',flush=True)
