"""Preserve the probe failure and restore byte-identical proofs for a clean-boot retry.

This does not waive GPU faults: all original per-boot monitors remain enabled.
It is restricted to the recorded diagnostic boot and two clean Gecko exits.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='020a8ad1-c7dc-4972-8844-1e502162863a'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert Path('/proc/sys/kernel/tainted').read_text().strip()=='4096'
sha=lambda data:hashlib.sha256(data).hexdigest()
state=Path('/var/lib/tzx')
assert json.loads((state/'cpu-full-failure.json').read_text())['boot_id']==boot
assert 'DATA_INVALID_FAULT' in json.loads((state/'cpu-full-failure.json').read_text())['error']
kernel=subprocess.check_output(['dmesg'],text=True)
faults=[s for s in kernel.splitlines() if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b',s,re.I)]
assert len(faults)==1 and '755.982727' in faults[0] and 'DATA_INVALID_FAULT' in faults[0],faults
for mode in ('default','noafbc'):
    record=json.loads(Path('/home/debian/browser-graphics-profile',mode+'.json').read_text())
    assert record['boot_id']==boot and record['clean_exit']==0 and record['new_kernel_messages']==[]
    graphics=record['troubleshoot']['value']['graphics']
    assert graphics['windowLayerManagerType']=='WebRender' and graphics['numAcceleratedWindows']==1
    assert graphics['webgl2Renderer']=='Mesa -- Mali-G57 (Panfrost)'
    assert record['canvas']['value']['frames']>=30
for component in ('tzx-cpu-full','tzx-gpu-devfreq','tzx-emmc-hs'):
    manifest=json.loads(Path('/usr/local/lib',component,'manifest.json').read_text())
    for name,digest in manifest['files'].items():assert sha(Path(name).read_bytes())==digest,name
subprocess.run(['python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'],check=True,timeout=20)
result=subprocess.check_output(['python3','/home/debian/verify_gpu_compute.py'],text=True,timeout=50)
assert 'MALI_G57_COMPUTE_ALL_WORDS_PASS' in result
assert all(int(s.rsplit(':',1)[1])==0 for s in Path('/sys/kernel/debug/mmc0/err_stats').read_text().splitlines())
for name in ('screen_buffer_errors','screen_panel_errors'):
    assert int(Path('/sys/module/tzx_display/parameters',name).read_text())==0
backup=Path('/root/tzx-recovery/app-launch-v1')
assert not backup.exists()
backup.mkdir(mode=0o700)
for name in ('cpu-full-failure.json','cpu-full-revoked.json','gpu-devfreq-failure.json','gpu-devfreq-revoked.json'):
    (backup/name).write_bytes((state/name).read_bytes())
(backup/'kernel-before-retry.txt').write_text(kernel)
(backup/'journal-before-retry.txt').write_text(subprocess.check_output(['journalctl','-b','--no-pager'],text=True))
proofs={'cpu-full':'c537a6d4f97b28c938b4dd88e40276d5d161b0c64ef6e234e06eeca7d5f4c368',
    'gpu-devfreq':'492f3beabf09d63b04c57a2b2c9dc4547b21af7886fd5ba0ee6da91309468ff1'}
for name,digest in proofs.items():
    data=(backup/(name+'-revoked.json')).read_bytes()
    assert sha(data)==digest
    target=state/(name+'-qualified.json')
    assert not target.exists()
    target.write_bytes(data);target.chmod(0o600)
trial={'status':'CLEAN_BOOT_RETRY_PENDING','failure_boot_id':boot,'prior_faults':faults,
    'original_proof_sha256':proofs,'guard_policy_unchanged':True,
    'cause':'Unresolved job data fault during overlapping browser startup/termination probes; no recurrence in two graceful graphics tests',
    'baseline_compute':result}
(backup/'retry.json').write_text(json.dumps(trial,indent=2)+'\n')
(state/'app-launch-retry.json').write_text(json.dumps(trial,indent=2)+'\n')
subprocess.run(['systemctl','reset-failed','tzx-cpu-dvfs','tzx-gpu-performance'],check=True)
os.sync()
print('ORIGINAL_PROOFS_RESTORED_FOR_MONITORED_CLEAN_BOOT_RETRY',json.dumps(trial),flush=True)
