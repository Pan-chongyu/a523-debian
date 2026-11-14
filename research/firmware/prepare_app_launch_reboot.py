"""Record the exact app overlay before its normal-reboot qualification."""
import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
installed=json.loads((state/'app-launch-installed.json').read_text())
controls=json.loads((state/'app-launch-controls-qualified.json').read_text())
assert controls['boot_id']==boot and controls['status']=='PASS'
subprocess.run(['python3','/home/debian/install_app_launch.py','verify'],check=True)
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
assert 'js fault' not in subprocess.check_output(['dmesg'],text=True)
record=dict(status='NORMAL_REBOOT_REQUESTED',boot_id_before=boot,files=installed['files'],controls=controls,
    benchmark_label='post-reboot-cold-'+boot[:8],
    toc0_sha256='1c2ce9324aae67cf5747c36249db0785c74d52c4094e4e735e37217f60800b41',
    script_sha256=hashlib.sha256(Path('/home/debian/profile_app_launch.py').read_bytes()).hexdigest())
target=state/'app-launch-reboot-request.json'
if target.exists():
    previous=json.loads(target.read_text());assert previous['boot_id_before']!=boot
    backup=Path('/root/tzx-recovery/app-launch-v1/overlay')/('reboot-request-'+previous['boot_id_before']+'.json')
    assert not backup.exists();backup.write_bytes(target.read_bytes())
target.write_text(json.dumps(record,indent=2)+'\n');os.sync()
print('APP_LAUNCH_NORMAL_REBOOT_REQUEST_SAVED',boot,record['benchmark_label'],flush=True)
