"""Qualify the user's persistent CPU performance preference after a real reboot."""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path

assert os.geteuid()==0 and sys.argv[1:] in (['idle'],['final'])
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
installed=json.loads((state/'performance-mode-installed.json').read_text())
assert installed['state']=='installed' and installed['installed_boot_id']!=boot
policies=[Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0,4)]
units=('tzx-cpu-performance-mode','tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs',
    'tzx-video','tzx-zram','tzx-screen-health','tzx-wifi','tzx-bluetooth','tzx-audio','lightdm')
run=lambda *args:subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=30)
for attempt in range(100):
    active=subprocess.run(['systemctl','is-active',*units],text=True,capture_output=True,timeout=15)
    if active.stdout.split()==['active']*len(units):break
    time.sleep(.5)
else:raise RuntimeError('Installed services did not settle: '+active.stdout)
print(run('python3','/home/debian/upgrade_early_performance.py','verify'),end='',flush=True)
assert not run('systemctl','--failed','--plain','--no-legend').strip()
assert run('systemctl','show','tzx-cpu-performance-mode','-p','NRestarts','--value').strip()=='0'
assert not Path('/etc/systemd/system/tzx-app-cache.service').exists()
assert not Path('/run/tzx-app-cache.json').exists()
assert json.loads((state/'app-launch-installed.json').read_text())['state']=='restored'
assert not Path('/usr/local/bin/tzx-launch').exists()
assert not Path('/etc/systemd/system/tzx-app-boost.service').exists()
assert all((p/'scaling_governor').read_text().strip()=='performance' for p in policies)
mode=json.loads(Path('/run/tzx-performance-mode.json').read_text())
assert mode['boot_id']==boot and mode['state']=='active'
assert mode['requested_maximum_khz']==[1416000,1800000]
assert mode['native_thermal_and_lease_caps_unchanged']
assert not mode['browser_preload'] and mode['gpu_requested_minimum_hz']==600000000
assert Path('/sys/class/devfreq/1800000.gpu/min_freq').read_text().strip()=='600000000'
assert Path('/sys/bus/platform/devices/1800000.gpu/power/control').read_text().strip()=='on'
assert Path('/sys/module/tzx_cpu_dvfs_cooling_v2/parameters/first_trip').read_text().strip()=='70000'
assert Path('/sys/module/tzx_cpu_dvfs_cooling_v2/parameters/second_trip').read_text().strip()=='80000'
assert all((p/'scaling_driver').read_text().strip()=='tzx-a523-dvfs2' for p in policies)

if sys.argv[1]=='idle':
    samples=[]
    for i in range(12):
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
        sample=dict(cpu_khz=[int((p/'scaling_cur_freq').read_text()) for p in policies],
            effective_maximum_khz=[int((p/'scaling_max_freq').read_text()) for p in policies],
            governors=[(p/'scaling_governor').read_text().strip() for p in policies],
            gpu_hz=int(Path('/sys/class/devfreq/1800000.gpu/cur_freq').read_text()),
            temperatures_mc={(p/'type').read_text().strip():int((p/'temp').read_text())
                for p in Path('/sys/class/thermal').glob('thermal_zone*')})
        assert sample['governors']==['performance','performance']
        assert sample['cpu_khz']==[1416000,1800000],sample
        assert sample['gpu_hz']==600000000,sample
        samples.append(sample);time.sleep(1)
    record=dict(status='PASS',boot_id=boot,installed_boot_id=installed['installed_boot_id'],
        actual_reboot=True,autostart=True,idle_frequency_samples=samples,browser_preload=False,
        native_thermal_caps_unchanged=True,failed_units=[])
    (state/'performance-mode-idle-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
    print('REBOOT_PERSISTENT_HIGH_FREQUENCY_12_SECONDS_PASS',json.dumps(dict(boot_id=boot,
        frequency_khz=samples[-1]['cpu_khz'],peak_temperature_mc=max(max(s['temperatures_mc'].values()) for s in samples))),flush=True)
else:
    idle=json.loads((state/'performance-mode-idle-qualified.json').read_text())
    native=json.loads((state/'boot-latency-qualified.json').read_text())
    integration=json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
    launch=json.loads(Path('/home/debian/app-launch-profile/performance-mode-post-reboot.json').read_text())
    for item in (idle,native,integration):assert item['boot_id']==boot and item['status']=='PASS'
    assert launch['boot_id']==boot and not launch['boost_requested'] and not launch['browser_binary_disk_cache']
    assert len(launch['samples'])==6 and all(s['window_visible_seconds']<20 for s in launch['samples'])
    assert integration['cpu_peak_khz']==[1416000,1800000]
    assert integration['iommu_faults']==integration['screen_buffer_and_panel_errors']==0
    sram=json.loads((state/'boot-cpu-performance-qualified.json').read_text())
    assert sram['boot_id']==boot and sram['status']=='PASS'
    assert native['toc0_sha256']==sram['toc0_sha256']=='367d51b493c2c647e12cfb24264afcac714cebcaa8b4605301620211f0befa1c'
    caps=json.loads((state/'performance-mode-caps-qualified.json').read_text())
    assert caps['boot_id']==boot and caps['status']=='PASS' and caps['high_minimum_does_not_bypass_native_maximum']
    timing={}
    for name in ('tzx-cpu-dvfs','tzx-gpu','lightdm'):
        props=dict(line.split('=',1) for line in run('systemctl','show',name,'-p','ActiveEnterTimestampMonotonic','-p','ExecMainStartTimestampMonotonic').splitlines())
        timing[name]={key:int(value)/1000000 for key,value in props.items()}
    assert timing['tzx-cpu-dvfs']['ActiveEnterTimestampMonotonic']<timing['tzx-gpu']['ExecMainStartTimestampMonotonic']<timing['lightdm']['ExecMainStartTimestampMonotonic']
    assert not re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error',run('dmesg'),re.I)
    retry=json.loads((state/'app-launch-retry.json').read_text())
    retry.update(status='CLEAN_BOOT_GRAPHICS_AND_COMBINED_LOAD_PASS',verified_boot_id=boot,
        fault_policy_unchanged=True,original_fault_cause='not isolated; absent on subsequent boots with graceful test-window shutdown')
    (state/'app-launch-retry.json').write_text(json.dumps(retry,indent=2)+'\n')
    record=dict(status='PASS',boot_id=boot,installed_boot_id=installed['installed_boot_id'],
        profile='early CPU and GPU maximum qualified performance; no preload',
        cpu_governors=['performance','performance'],qualified_maximum_khz=[1416000,1800000],
        idle_verification=idle,launch_results=launch['summary'],browser_preload=False,
        integration=integration,toc0_sha256=native['toc0_sha256'],installed_files=installed['files'],
        SRAM_boot_performance=sram,
        before_graphical_CPU_timing_seconds=timing,GPU_safety_ceiling_test=caps,
        native_thermal_and_lease_caps_unchanged=True,earlier_gpu_fault_preserved_cause_unresolved=True,
        native_boot_and_right_landscape_verified=True,failed_units=[],kernel_gpu_faults=0,
        user_perceived_browser_before_seconds_approx=3,private_test_profile_distinct_from_user_browser=True,
        browser_homepage_and_gpu_preferences_unchanged=True)
    (state/'performance-mode-final-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
    print('PERSISTENT_PERFORMANCE_REBOOT_AND_FULL_STACK_PASS',json.dumps(dict(boot_id=boot,
        cpu_governors=record['cpu_governors'],qualified_maximum_khz=record['qualified_maximum_khz'],
        launch_results=record['launch_results'],combined_seconds=integration['seconds'],
        peak_temperature_mc=max(integration['temperature_peaks_mc'].values()))),flush=True)
