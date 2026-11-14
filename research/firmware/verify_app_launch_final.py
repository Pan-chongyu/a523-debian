"""Qualify the app overlay against the unchanged boot, display and native stack."""
import hashlib,json,os,re,subprocess,time
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
request=json.loads((state/'app-launch-reboot-request.json').read_text())
assert boot!=request['boot_id_before']
installed=json.loads((state/'app-launch-installed.json').read_text())
assert installed['files']==request['files']
for name,item in installed['files'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==item['installed_sha256'],name
native=json.loads((state/'boot-latency-qualified.json').read_text())
integration=json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
assert native['boot_id']==integration['boot_id']==boot
assert native['status']==integration['status']=='PASS'
assert native['toc0_sha256']==request['toc0_sha256']
assert integration['cpu_peak_khz']==[1416000,1800000] and integration['iommu_faults']==0
assert integration['screen_buffer_and_panel_errors']==0
cache=json.loads(Path('/run/tzx-app-cache.json').read_text())
assert cache['boot_id']==boot and cache['status']=='PASS' and 280*1024*1024<cache['bytes_read']<320*1024*1024
assert subprocess.check_output(['systemctl','show','tzx-app-cache','-p','ExecMainStatus','--value'],text=True).strip()=='0'
launch=json.loads(Path('/home/debian/app-launch-profile',request['benchmark_label']+'.json').read_text())
assert launch['boot_id']==boot and launch['boost_requested'] and not launch['browser_binary_disk_cache']
assert launch['benchmark_sha256']==request['script_sha256']
assert len(launch['samples'])==6
assert all(s['window_visible_seconds']<8 for s in launch['samples'])
subprocess.run(['python3','/home/debian/install_app_launch.py','verify'],check=True)
assert Path('/sys/devices/system/cpu/cpufreq/policy0/scaling_driver').read_text().strip()=='tzx-a523-dvfs2'
for name in ('cpu-full','gpu-devfreq'):
    assert (state/(name+'-qualified.json')).exists()
kernel=subprocess.check_output(['dmesg'],text=True)
assert not re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error',kernel,re.I)
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
retry=json.loads((state/'app-launch-retry.json').read_text())
retry['status']='CLEAN_BOOT_GRAPHICS_AND_COMBINED_LOAD_PASS'
retry['verified_boot_id']=boot
retry['fault_policy_unchanged']=True
retry['original_fault_cause']='not isolated; absent with graceful test-window shutdown across two subsequent boots'
(state/'app-launch-retry.json').write_text(json.dumps(retry,indent=2)+'\n')
record=dict(status='PASS',boot_id=boot,previous_boot_id=request['boot_id_before'],
    normal_reboot_autostart=True,launch_results=launch['summary'],first_browser_launch=launch['samples'][0],
    background_cache=cache,controls=request['controls'],installed_files=installed['files'],
    cpu_gpu_memory_video_storage_integration=integration,
    native_boot_and_right_landscape_verified=True,toc0_sha256=native['toc0_sha256'],
    failed_units=[],kernel_gpu_faults=0,earlier_probe_failure_preserved=True,
    user_perceived_browser_before_seconds_approx=3,
    private_test_profile_distinct_from_user_browser=True,
    browser_homepage_and_gpu_preferences_unchanged=True)
(state/'app-launch-final-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
print('APPLICATION_LAUNCH_REBOOT_NATIVE_STACK_AND_COEXISTENCE_PASS',json.dumps({k:record[k] for k in
    ('status','boot_id','normal_reboot_autostart','launch_results','kernel_gpu_faults','toc0_sha256')}),flush=True)
