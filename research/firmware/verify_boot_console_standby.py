"""Run the existing real panel sleep test and restore the desktop DPMS policy."""
import os
import subprocess

assert os.geteuid() == 0
env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/run/lightdm/root/:0')


def x(*args):
    return subprocess.check_output(['xset', *args], env=env, text=True,
                                   stderr=subprocess.STDOUT, timeout=20)


settings = x('q')
enabled = 'DPMS is Enabled' in settings
try:
    x('+dpms')
    subprocess.run(['python3', '/home/debian/verify_screen_standby.py'], check=True,
                   timeout=100)
finally:
    x('dpms', 'force', 'on')
    if not enabled:
        x('-dpms')
assert ('DPMS is Enabled' in x('q')) == enabled
print('BOOT_CONSOLE_FIVE_SLEEP_WAKE_CYCLES_AND_DESKTOP_POLICY_RESTORED', flush=True)
