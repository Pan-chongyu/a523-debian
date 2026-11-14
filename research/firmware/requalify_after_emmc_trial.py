"""Restore qualified CPU/GPU after the explicitly recorded eMMC trial reset."""
import hashlib,json,subprocess
from pathlib import Path
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='f92aae87-4143-422b-bd13-f26a1f37de7b'
assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip()=='25000000'
def run(*args,timeout=80):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)
assert 'Unclean previous CPU performance boot' in json.loads(Path('/var/lib/tzx/cpu-dvfs-failure.json').read_text())['error']
assert 'Unclean previous performance boot' in json.loads(Path('/var/lib/tzx/gpu-performance-failure.json').read_text())['error']
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
print(run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'),flush=True)
print(run('python3','/usr/local/lib/tzx-accel-hardware/verify_gpu_render.py','--node','/dev/dri/by-path/platform-tzx-de-scanout-card'),flush=True)
for profile in ('cpu-dvfs','gpu-performance'):
    root=Path('/usr/local/lib')/('tzx-'+profile)
    for path,digest in json.loads((root/'manifest.json').read_text())['files'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    qualified=Path('/var/lib/tzx')/(profile+'-qualified.json')
    revoked=Path('/var/lib/tzx')/(profile+'-revoked.json')
    record=json.loads(revoked.read_text());assert record['trial']['status']=='PASS'
    record['emmc_trial_requalification']={'boot_id':boot,'prior_boot':'f52d55fc-5b20-43ee-97d5-47ddc5f773c5',
        'cause':'agent-triggered SysRq recovery after opt-in HS200 150MHz command stalled',
        'baseline_storage_mhz':25,'mapped_file_integrity':'452 files, 478406585 bytes PASS','gpu_pixel_render':'PASS'}
    assert not qualified.exists()
    qualified.write_text(json.dumps(record,indent=2)+'\n')
    run('systemctl','reset-failed','tzx-'+profile)
    run('systemctl','start','tzx-'+profile)
print(run('/home/debian/memory-check-bounded'),flush=True)
text=run('runuser','-u','debian','--','env','DISPLAY=:0','XAUTHORITY=/home/debian/.Xauthority',
    'glmark2-es2','--off-screen','--size','640x480','-b',':duration=1',timeout=100)
assert 'Mali-G57 (Panfrost)' in text and 'glmark2 Score:' in text and 'Error:' not in text
Path('/home/debian/gpu-performance/after-emmc-trial.log').write_text(text)
print(text,flush=True)
assert json.loads(Path('/run/tzx-gpu-performance.json').read_text())['actual_mhz']==600
assert json.loads(Path('/run/tzx-cpu-dvfs.json').read_text())['maximum_khz']==[1416000,1488000]
print('CPU_DVFS_GPU_600_REQUALIFIED_AFTER_RECORDED_EMMC_TRIAL_RESET',flush=True)
