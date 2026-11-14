"""Freeze current normal-boot qualification and unchanged early boot identity."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

STATE = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
prior = json.loads((STATE/'performance-reboot-qualified.json').read_text())
assert prior['status'] == 'PASS' and prior['boot_id'] != boot
proof_path = STATE/'emmc-performance-validation-reboot.json'
proof = json.loads(proof_path.read_text())
assert proof['status'] == 'PASS' and proof['boot_id'] == boot and proof['normal_reboot_verified']
assert proof['actual_cpu_maximum_khz'] == [792000,1008000]
assert proof['eMMC_actual_clock_hz'] == 50000000 and proof['gpu_hz'] == 600000000
for kind,key in (('screen','result'),('dram-gpu','status')):
    health = json.loads((STATE/(kind+'-boot-health.json')).read_text())
    assert health['boot_id'] == boot and health[key] == 'PASS'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
installed = {}
for kind in ('cpu','gpu','emmc'):
    manifest = json.loads((Path('/usr/local/lib/tzx-'+kind+'-performance')/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest,name
    installed[kind] = manifest
wifi = json.loads((STATE/'wifi-performance-installed.json').read_text())
for name,digest in wifi['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest,name
assert 'actual clock:\t22222222 Hz' in Path('/sys/kernel/debug/mmc1/ios').read_text()
subprocess.run(['systemctl','is-active','tzx-cpu-performance.service','tzx-gpu-performance.service',
                'tzx-emmc-performance.service','tzx-wifi.service','tzx-bluetooth.service'],check=True)
assert not subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip()
fd = os.open('/dev/mmcblk0',os.O_RDONLY)
try:
    identities = {'trained_TOC0':hashlib.sha256(os.pread(fd,40960,256*512)).hexdigest(),
                  'active_header':hashlib.sha256(os.pread(fd,512,4096*512)).hexdigest()}
finally:
    os.close(fd)
assert identities == {
    'trained_TOC0':'311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75',
    'active_header':'6b7ebd8607b02e0a0c1230dcabdbeada6ac8217ede73e3e45cb70a9b59a5e409'}
idle = []
for unused in range(25):
    idle.append({'cpu_khz':[int(Path('/sys/devices/system/cpu/cpufreq/policy'+str(n)+'/scaling_cur_freq').read_text()) for n in (0,4)],
                 'gpu_runtime':Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip()})
    time.sleep(0.4)
assert [min(s['cpu_khz'][n] for s in idle) for n in (0,1)] == [120000,120000]
assert any(s['gpu_runtime'] == 'suspended' for s in idle)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
record = {'status':'PASS','previous_boot_id':prior['boot_id'],'boot_id':boot,
    'normal_reboot_verified':True,'poweroff_key_on_verified':False,
    'prior_CPU_GPU_WiFi_normal_reboot_proof_sha256':hashlib.sha256((STATE/'performance-reboot-qualified.json').read_bytes()).hexdigest(),
    'combined_storage_GPU_CPU_load_proof':proof,
    'combined_load_sha256':hashlib.sha256(proof_path.read_bytes()).hexdigest(),
    'actual_manifests':installed,'wifi_files':wifi['files'],'early_boot_hashes_unchanged':identities,
    'idle_cpu_minimum_khz':[120000,120000],'gpu_auto_suspend':True,'idle_samples':idle,
    'screen_orientation':'1280x800 right; fbcon rotate=1; matching touch matrix',
    'boot_areas_changed':False,'failed_units':[]}
target = STATE/'performance-storage-reboot-qualified.json'
assert not target.exists()
target.write_text(json.dumps(record,indent=2)+'\n')
for kind in ('cpu','gpu','emmc','wifi'):
    for suffix in (('installed',) if kind == 'wifi' else ('installed','qualified')):
        p = STATE/(kind+'-performance-'+suffix+'.json')
        state = json.loads(p.read_text())
        state['normal_reboot_verified'] = True
        state['normal_reboot_id'] = boot
        state['poweroff_key_on_verified'] = False
        if suffix == 'installed':
            state['state'] = 'installed-normal-reboot-qualified'
        else:
            state['scope'] = 'online tests and real normal reboot passed; poweroff/key-on not yet tested'
        state['latest_combined_boot_validation'] = {'status':'PASS','boot_id':boot,
            'record':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'normal_reboot_verified':True,'poweroff_key_on_verified':False}
        temp = p.with_suffix('.json.storageproof')
        temp.write_text(json.dumps(state,indent=2)+'\n')
        temp.replace(p)
subprocess.run(['sync'],check=True)
print('PERFORMANCE_STORAGE_SECOND_NORMAL_REBOOT_QUALIFIED',json.dumps({
    'boot_id':boot,'previous_boot_id':prior['boot_id'],'CPU_khz':[792000,1008000],
    'GPU_hz':600000000,'eMMC_hz':50000000,'idle_cpu_khz':[120000,120000],
    'normal_reboot_verified':True,'poweroff_key_on_verified':False}))
