"""Install a separate logger runtime with an explicit original-runtime rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--restore',action='store_true')
args=parser.parse_args()
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1'
assert '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
sha=lambda data:hashlib.sha256(data).hexdigest()
original=Path('/usr/local/lib/tzx-rtc-log')
assert sha((original/'runtime.py').read_bytes())=='abdc2ef987d49e1778cbc464620767587cbeee001e87411b35aa9792209f1bf4'
assert sha((original/'tzx_rtc_log.ko').read_bytes())=='80e8e0522faec7ead866a254667a3272ccd6939551ed2f13bce0f2aa1b3fca73'
stage=Path('/home/debian/rtc-context')
pins={'runtime.py':'b1045903561eca454a7e9fe8158d5df29de37047ec31a2555a0dfb986a005738',
    'tzx_rtc_log.ko':'bb446382bdfec6fb87120540f67bd521851149538547f3c162697a2bb9eb22bb',
    'rtc_context_codec.py':'c1f02165b4c7c2b495bdcbddd33ac5eaa331fec1309e0d970462e42971f92bbf'}
target=Path('/usr/local/lib/tzx-rtc-context')
dropin=Path('/etc/systemd/system/tzx-rtc-log.service.d/97-abort-context.conf')
dropin_text='[Service]\nExecStart=\nExecStart=/usr/bin/python3 /usr/local/lib/tzx-rtc-context/runtime.py\n'
def run(*command):
    subprocess.run(command,check=True,timeout=30)
if args.restore:
    assert dropin.read_text()==dropin_text
    run('python3',str(target/'runtime.py'),'--live')
else:
    assert not dropin.exists()
    for name,digest in pins.items():
        data=(stage/name).read_bytes()
        assert sha(data)==digest,name
        path=target/name
        target.mkdir(exist_ok=True)
        assert not path.exists()
        path.write_bytes(data)
        path.chmod(0o644)
        assert sha(path.read_bytes())==digest
    run('python3',str(original/'runtime.py'),'--live')
run('systemctl','stop','tzx-rtc-log.service')
try:
    run('rmmod','tzx_rtc_log')
    if args.restore:dropin.unlink()
    else:
        dropin.parent.mkdir(exist_ok=True,parents=True)
        dropin.write_text(dropin_text)
    run('systemctl','daemon-reload')
    run('systemctl','start','tzx-rtc-log.service')
    run('python3',str((original if args.restore else target)/'runtime.py'),'--live')
except BaseException:
    if Path('/sys/module/tzx_rtc_log').exists():
        run('rmmod','tzx_rtc_log')
    dropin.unlink(missing_ok=True)
    run('systemctl','daemon-reload')
    run('systemctl','reset-failed','tzx-rtc-log.service')
    run('systemctl','start','tzx-rtc-log.service')
    raise
os.sync()
print('RTC_CONTEXT_RUNTIME_RESTORED' if args.restore else 'RTC_CONTEXT_RUNTIME_INSTALLED_AND_ARMED',flush=True)
