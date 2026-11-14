"""Record this CPU/GPU profile before normal PMIC off and physical key-on."""
import hashlib,json,os,subprocess,time
from pathlib import Path
assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'cpu-gpu-normal-reboot-qualified.json').read_text())
assert proof['boot_id']==boot and proof['status']=='PASS'
target=state/'cpu-gpu-key-on-request.json'
assert not target.exists()
sha=lambda b:hashlib.sha256(b).hexdigest()
def run(*args,timeout=80):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)
assert not run('systemctl','--failed','--no-legend','--plain').strip()
assert run('systemctl','is-active','tzx-cpu-dvfs','tzx-gpu-performance','tzx-pmic-poweroff','tzx-emmc-hs').split()==['active']*4
installed=json.loads((state/'pmic-poweroff-installed.json').read_text())
assert installed['poweroff_tested'] and installed['unit_enabled']
for path,digest in installed['files'].items():assert sha(Path('/'+path).read_bytes())==digest,path
assert Path('/sys/module/tzx_pmic_poweroff/parameters/armed').read_text().strip()=='Y'
for name in ('cpu-full','gpu-devfreq','emmc-hs'):
    manifest=json.loads((Path('/usr/local/lib')/('tzx-'+name)/'manifest.json').read_text())
    for path,digest in manifest['files'].items():assert sha(Path(path).read_bytes())==digest,path
pmic=json.loads(run('python3','/usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py'))
assert int(pmic['axp717']['0x27'],16)==8
record=dict(state='normal_poweroff_requested_physical_key_on_pending',previous_boot_id=boot,
    requested_unix=int(time.time()),before_pmic=pmic,
    before_screen=json.loads((state/'screen-boot-health.json').read_text()),
    previous_normal_reboot_proof_sha256=sha((state/'cpu-gpu-normal-reboot-qualified.json').read_bytes()),
    method='systemctl poweroff; existing qualified AXP717 POWER_OFF_PREPARE; user physical power key',
    battery_and_USB_removal_required=False)
temp=target.with_suffix('.json.new')
with temp.open('w') as stream:
    json.dump(record,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
temp.replace(target);os.sync()
print('CPU_GPU_NORMAL_POWEROFF_PHYSICAL_KEY_ON_TEST_REQUESTED',json.dumps(record),flush=True)
print(run('systemd-run','--unit=tzx-cpu-gpu-physical-key-on-test','--on-active=3s',
    '/usr/bin/systemctl','poweroff'),flush=True)
