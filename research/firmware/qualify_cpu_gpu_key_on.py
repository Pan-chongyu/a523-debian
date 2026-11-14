"""Audit the same CPU/GPU profile after PMIC off and physical key-on."""
import gzip,hashlib,json,os,re,subprocess,time
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
request=json.loads((state/'cpu-gpu-key-on-request.json').read_text())
warm=json.loads((state/'cpu-gpu-normal-reboot-qualified.json').read_text())
assert warm['status']=='PASS' and warm['normal_reboot_verified']
assert request['previous_boot_id']!=boot
sha=lambda b:hashlib.sha256(b).hexdigest()
def run(*args,timeout=90):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert sha(gzip.decompress(Path('/proc/config.gz').read_bytes()))=='8228e905b2ae482d57f071c901a63888497b93de969049659151d6abeb1cff97'
assert sha(Path('/boot/Image').read_bytes())=='470dd0c350c7ef7aad392eac3a35237672862f0fffdacea8da4e6adb6740e6e4'
assert '#5 ' in os.uname().version
pmic=json.loads(run('python3','/usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py'))
assert pmic['boot_id']==boot and pmic['axp323_id']=='0x49'
assert int(pmic['axp717']['0x21'],16)&2, 'No PMIC software shutdown reason'
assert int(pmic['axp717']['0x21'],16)&0xf8==0, 'Undervoltage/current/thermal shutdown reason'
assert int(pmic['axp717']['0x20'],16)&1, 'No PMIC physical key-on reason'
assert int(pmic['axp717']['0x27'],16)==8 and pmic['axp717']['0x85']=='0xc9'
print('PMIC_SOFTWARE_OFF_AND_PHYSICAL_KEY_ON_CAUSES_PASS',json.dumps(pmic),flush=True)
units=('tzx-cpu-dvfs','tzx-gpu-performance','tzx-gpu','tzx-video','tzx-zram','tzx-emmc-hs',
       'tzx-wifi','tzx-bluetooth','tzx-audio','tzx-display','tzx-touch','tzx-screen-health')
assert run('systemctl','is-active',*units).split()==['active']*len(units)
assert run('systemctl','is-enabled','tzx-cpu-dvfs','tzx-gpu-performance','tzx-video','tzx-zram','tzx-emmc-hs').split()==['enabled']*5
assert not run('systemctl','--failed','--no-legend','--plain').strip()
health={}
for name,key in (('screen-boot-health','result'),('dram-gpu-boot-health','status')):
    value=json.loads((state/(name+'.json')).read_text())
    assert value['boot_id']==boot and value[key]=='PASS'
    health[name]=value
screen=health['screen-boot-health']
assert 'current 1280 x 800' in screen['xrandr'] and ' right ' in screen['xrandr']
assert screen['display_setup']['fbcon_rotate']=='1'
assert '0.000000, 1.000000, 0.000000, -1.000000, 0.000000, 1.000000' in screen['display_setup']['touch_properties']
assert Path('/sys/class/graphics/fbcon/rotate').read_text().strip()=='1'
manifests={}
for name in ('cpu-full','gpu-devfreq','emmc-hs'):
    manifest=json.loads((Path('/usr/local/lib')/('tzx-'+name)/'manifest.json').read_text())
    for path,digest in manifest['files'].items():assert sha(Path(path).read_bytes())==digest,path
    manifests[name]=manifest
cpu=Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters')
assert int((cpu/'sid_dvfs_word').read_text())==0x48
assert int((cpu/'vf_index').read_text())==0x0300
assert [int(Path('/sys/devices/system/cpu/cpu%d/cpu_capacity'%n).read_text()) for n in range(8)]==[725]*4+[1024]*4
gpu=Path('/sys/class/devfreq/1800000.gpu')
assert [int(v) for v in (gpu/'available_frequencies').read_text().split()]==[150000000,200000000,300000000,400000000,600000000]
assert (gpu/'governor').read_text().strip()=='simple_ondemand'
guard=Path('/sys/module/tzx_gpu_devfreq_guard/parameters')
assert [(guard/n).read_text().strip() for n in ('first_trip','second_trip','fault_trip','lease_seconds')]==['65000','70000','85000','30']
assert int((guard/'fault').read_text())==0
assert any((p/'type').read_text().strip()=='devfreq-1800000.gpu' for p in Path('/sys/class/thermal').glob('cooling_device*'))
zone=next(p for p in Path('/sys/class/thermal').glob('thermal_zone*') if (p/'type').read_text().strip()=='tzx-board-thermal')
assert len(list(zone.glob('cdev*trip_point')))==6
assert [(zone/('trip_point_%d_temp'%i)).read_text().strip() for i in range(5)]==['65000','70000','70000','80000','95000']
print('NATIVE_CPU_GPU_ACTUAL_AUTOSTART_AND_SCREEN_PASS',boot,flush=True)
print(run('python3','-u','/home/debian/verify_cpu_gpu_integration.py',timeout=220),end='',flush=True)
combined=json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
assert combined['boot_id']==boot and combined['status']=='PASS'
audit=run('python3','/home/debian/verify_safe_memory.py','--files-only',timeout=120)
assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
print(audit,end='',flush=True)
idle=[]
for unused in range(40):
    idle.append(dict(cpu_khz=[int(Path('/sys/devices/system/cpu/cpufreq/policy%d/scaling_cur_freq'%n).read_text()) for n in (0,4)],
        gpu_runtime=Path('/sys/bus/platform/devices/1800000.gpu/power/runtime_status').read_text().strip(),
        gpu_hz=int((gpu/'cur_freq').read_text())))
    time.sleep(.4)
assert [min(v['cpu_khz'][n] for v in idle) for n in (0,1)]==[120000,120000]
assert any(v['gpu_runtime']=='suspended' for v in idle),idle
statuses={}
for name,pending in (('cpu-dvfs','cpu-full'),('gpu-performance','gpu-devfreq'),('emmc-hs','emmc-hs')):
    value=json.loads(Path('/run/tzx-'+name+'.json').read_text())
    assert value['boot_id']==boot and value['state']=='active'
    assert json.loads((state/(pending+'-pending.json')).read_text())['boot_id']==boot
    statuses[name]=value
assert statuses['cpu-dvfs']['maximum_khz']==[1416000,1800000]
assert statuses['gpu-performance']['clock_owner']=='Panfrost devfreq'
assert statuses['emmc-hs']['actual_hz']==100000000
assert not run('systemctl','--failed','--no-legend','--plain').strip()
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
assert not [s for s in run('dmesg').splitlines() if re.search(r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error',s,re.I)]
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
print(run('python3','/home/debian/cpu-gpu-kernel/install_cpu_gpu_kernel.py','verify-boot',
    'e78bb5b096326a97915d09dbf93b12a106000d0faa8ff8f058c9e79363179007',timeout=80),end='',flush=True)
record=dict(status='PASS',previous_boot_id=request['previous_boot_id'],boot_id=boot,
    normal_reboot_verified=True,normal_reboot_id=warm['boot_id'],poweroff_key_on_verified=True,
    pmic_status=pmic,visual_confirmation='pending',complete_battery_USB_removal_tested=False,installed_manifests=manifests,
    runtime_statuses=statuses,boot_health=health,combined_load=combined,file_audit=audit,
    idle_cpu_minimum_khz=[120000,120000],gpu_autosuspend=True,idle_samples=idle,
    gpu_guard_peak_temperature_mc=int((guard/'peak_temperature_mc').read_text()),
    failed_units=[],screen_orientation='right 1280x800',
    limits=['vf0300 permits big 1.8GHz; its 1.992GHz OPP is disabled by the vendor table',
        'GPU uses qualified 150-600MHz OPPs at fixed existing 900mV; 800MHz unqualified',
        'OpenGL ES 3.1 compute qualified; Vulkan/OpenCL not integrated',
        'Deep CPU idle, CPU hotplug and EAS energy model not integrated',
        'PMIC soft-off/key-on verified with battery and USB attached; not full removal of power',
        'HS400, browser decode and full-rate desktop video remain outside this result'])
target=state/'cpu-gpu-key-on-qualified.json'
target.write_text(json.dumps(record,indent=2)+'\n')
for name in ('cpu-full-qualified','gpu-devfreq-qualified','cpu-gpu-native-installed'):
    path=state/(name+'.json');value=json.loads(path.read_text())
    value.update(poweroff_key_on_verified=True,poweroff_key_on_boot_id=boot,
        poweroff_key_on_proof_sha256=sha(target.read_bytes()))
    if name.endswith('installed'):value['state']='actual-normal-and-physical-key-on-load-verified'
    else:value['scope']='Qualified online, normal reboot and PMIC soft-off/physical key-on with concurrent load'
    path.write_text(json.dumps(value,indent=2)+'\n')
os.sync()
print('CPU_GPU_PHYSICAL_KEY_ON_FULL_STACK_QUALIFIED',json.dumps(dict(boot_id=boot,
    cpu_max_khz=[1416000,1800000],gpu_native_mhz=[150,200,300,400,600],
    gpu_autosuspend=True,cpu_idle_khz=[120000,120000],right_landscape=True)),flush=True)
