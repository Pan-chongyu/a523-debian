"""Record the human observations for this exact completed hardware test."""
import json
import os
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='8950abe9-0201-451a-b95c-b2b6b6d4062b'
observations=dict(boot_id=boot,right_landscape_and_touch_confirmed=True,
    source='Human replies in this task; approximate manual stopwatch measurements',
    normal_trials=[
        dict(boot_id='e9819089-96cb-4220-b33b-0c43dd62bbae',reported_seconds_approx=26,
             user_reply='26s 桌面 触摸正常',right_landscape_and_touch_confirmed=True),
        dict(boot_id='5caa2c4d-80ef-4397-8c25-3e59083b1651',reported_seconds_approx=28,
             user_reply='28s 桌面触摸正常',right_landscape_and_touch_confirmed=True)],
    PMIC_key_on=dict(boot_id=boot,physical_key_to_first_light_seconds_approx=25,
        physical_key_to_desktop_seconds_approx=49,
        user_timing_reply='按下开机亮屏25s，按下开机键到桌面49s',
        user_display_touch_reply='横屏、触摸都正常'),
    complete_removal_of_power_tested=False)
(state/'screen-fast-user-confirmed.json').write_text(json.dumps(observations,indent=2,ensure_ascii=False)+'\n')
for name in ('screen-fast-key-on-qualified','screen-fast-qualified','screen-fast-final-qualified'):
    path=state/(name+'.json')
    value=json.loads(path.read_text())
    assert value['status']=='PASS' and value['boot_id']==boot
    value['visual_confirmation']=observations
    path.write_text(json.dumps(value,indent=2)+'\n')
path=state/'screen-fast-installed.json'
value=json.loads(path.read_text())
assert value['verified_boot_id']==boot
value.update(state='normal-reboot-PMIC-key-on-load-and-user-verified',
    poweroff_key_on_verified=True,user_right_landscape_and_touch_confirmed=True)
path.write_text(json.dumps(value,indent=2)+'\n')
os.sync()
print('SCREEN_FAST_USER_FIRST_LIGHT_DESKTOP_AND_TOUCH_CONFIRMED',json.dumps(observations,ensure_ascii=False),flush=True)
