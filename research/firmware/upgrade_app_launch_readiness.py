"""Wait for actual CPU readiness instead of racing Type=exec module replacement."""
import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx/app-launch-installed.json')
root=Path('/usr/local/lib/tzx-app-launch');stage=Path('/home/debian/app-launch-stage')
installed=json.loads(state.read_text());assert installed['state']=='installed'
sha=lambda b:hashlib.sha256(b).hexdigest()
for name,item in installed['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
manifest=json.loads((root/'manifest.json').read_text())
incoming=json.loads((stage/'manifest.json').read_text())
targets={root/'boost.py':'boost.py',Path('/etc/systemd/system/tzx-app-boost.service'):'tzx-app-boost.service'}
assert sha((root/'boost.py').read_bytes())=='d458c01521676e493381fe538254300ec5c0b4938083976684aa49b6efbf8160'
assert b'CPU owner did not finish initializing' in (stage/'boost.py').read_bytes()
assert b'TimeoutStartSec=30' in (stage/'tzx-app-boost.service').read_bytes()
backup=Path('/root/tzx-recovery/app-launch-v1/overlay/readiness-fix');assert not backup.exists()
backup.mkdir(mode=0o700)
(backup/'installed-before.json').write_bytes(state.read_bytes())
(backup/'manifest-before.json').write_bytes((root/'manifest.json').read_bytes())
(backup/'journal-before.txt').write_text(subprocess.check_output(['journalctl','-b','-u','tzx-app-boost','--no-pager'],text=True))
for target,name in targets.items():(backup/name).write_bytes(target.read_bytes())
subprocess.run(['systemctl','stop','tzx-app-boost'],check=True,timeout=10)
for target,name in targets.items():
    data=(stage/name).read_bytes();assert sha(data)==incoming['files'][name]
    target.write_bytes(data)
    manifest['files'][str(target)]=sha(data)
    installed['files'][str(target)]['installed_sha256']=sha(data)
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
installed['files'][str(root/'manifest.json')]['installed_sha256']=sha((root/'manifest.json').read_bytes())
installed['readiness_revision']=2
state.write_text(json.dumps(installed,indent=2)+'\n');os.sync()
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','start','tzx-app-boost'],check=True,timeout=35)
print('APP_BOOST_REAL_CPU_READINESS_WAIT_INSTALLED',flush=True)
