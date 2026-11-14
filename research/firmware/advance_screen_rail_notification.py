"""Overlap the unchanged touch settle delay with independent display preparation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.geteuid() == 0
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot == 'e9819089-96cb-4220-b33b-0c43dd62bbae'
assert Path('/proc/sys/kernel/tainted').read_text().strip() == '4096'
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
state = Path('/var/lib/tzx/screen-fast-installed.json')
installed = json.loads(state.read_text())
sha = lambda b: hashlib.sha256(b).hexdigest()
for name, item in installed['files'].items():
    assert sha(Path(name).read_bytes()) == item['installed_sha256'], name
backup = Path('/root/tzx-recovery/screen-fast-rail-v1/before-earlier-notification')
assert not backup.exists()
script = Path('/usr/local/lib/tzx-peripherals-accel1/tzx-touch-runtime-test.sh')
helper = Path('/usr/local/lib/tzx-screen-fast/touch_ready.py')
old_script = script.read_bytes()
old_helper = helper.read_bytes()
before = (b'    sleep 1\n    if test -n "${NOTIFY_SOCKET:-}"; then\n'
    b'        /usr/bin/python3 /usr/local/lib/tzx-screen-fast/touch_ready.py rails\n    fi\n')
after = (b'    if test -n "${NOTIFY_SOCKET:-}"; then\n'
    b'        /usr/bin/python3 /usr/local/lib/tzx-screen-fast/touch_ready.py rails\n    fi\n    sleep 1\n')
assert old_script.count(before) == 1
new_script = old_script.replace(before, after)
new_helper = Path('/home/debian/screen_fast_touch_ready.py').read_bytes()
assert new_helper == old_helper.replace(b'CLDO2-ready-after-original-one-second-settle',
    b'CLDO2-enabled-before-original-touch-settle')
backup.mkdir()
(backup/'touch-runtime').write_bytes(old_script)
(backup/'touch_ready.py').write_bytes(old_helper)
(backup/'installed.json').write_bytes(state.read_bytes())
for path, data in ((script,new_script),(helper,new_helper)):
    temporary = path.with_name(path.name+'.screen-fast-new')
    temporary.write_bytes(data)
    temporary.chmod(0o644)
    temporary.replace(path)
    installed['files'][str(path)]['installed_sha256'] = sha(data)
installed.update(state='earlier-notification-pending-next-normal-reboot',
    original_touch_settle_preserved_before_probe=True,
    notification_moved_before_touch_settle=True, notification_change_boot_id=boot)
state.write_text(json.dumps(installed,indent=2)+'\n')
os.sync()
subprocess.run(['python3','/home/debian/install_screen_fast_boot.py','verify'],check=True,timeout=40)
print('DISPLAY_MAY_INITIALIZE_DURING_UNCHANGED_TOUCH_SETTLE',flush=True)
