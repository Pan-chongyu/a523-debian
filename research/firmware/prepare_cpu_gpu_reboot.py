"""Record the installed integration result before an actual normal reboot."""
import hashlib,json,os,subprocess,time
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state=Path('/var/lib/tzx')
proof=json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
assert proof['status']=='PASS' and proof['boot_id']==boot
assert proof['cpu_peak_khz']==[1416000,1800000]
assert proof['iommu_faults']==proof['screen_buffer_and_panel_errors']==0
assert not subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip()
for name in ('tzx-cpu-full','tzx-gpu-devfreq','tzx-emmc-hs'):
    manifest=json.loads((Path('/usr/local/lib')/name/'manifest.json').read_text())
    for path,digest in manifest['files'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
record=dict(previous_boot_id=boot,requested_unix=int(time.time()),
    normal_reboot=True,physical_key_on=False,combined_load=proof)
(state/'cpu-gpu-normal-reboot-request.json').write_text(json.dumps(record,indent=2)+'\n')
os.sync()
print('CPU_GPU_NORMAL_REBOOT_REQUESTED',boot,flush=True)
subprocess.run(['systemd-run','--unit=tzx-cpu-gpu-qualification-reboot','--on-active=3s',
    '/usr/bin/systemctl','reboot'],check=True,timeout=20)
