"""Exercise the installed CPU, RAM, GPU, VPU and HS200 stack together."""
import hashlib,json,os,re,subprocess,time
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
folder=Path('/home/debian/cpu-gpu-validation');folder.mkdir(exist_ok=True)
units=('tzx-cpu-dvfs','tzx-gpu-performance','tzx-video','tzx-zram','tzx-emmc-hs')
param=Path('/sys/module/tzx_emmc_hs_lease/parameters')
maximum=[0,0];peaks={};children=[];streams=[];gpu_rates=set()
started=time.monotonic()
errors=Path('/sys/kernel/debug/mmc0/err_stats').read_text()
assert all(int(s.rsplit(':',1)[1])==0 for s in errors.splitlines())
xorg=subprocess.check_output(['pgrep','-x','Xorg'],text=True).strip()
def irq(name):
    row=next(s for s in Path('/proc/interrupts').read_text().splitlines() if s.rstrip().endswith(name))
    return sum(map(int,row.split(':',1)[1].split()[:8]))
def sample():
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
    assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
    assert Path('/sys/kernel/debug/mmc0/err_stats').read_text()==errors
    assert 'mmc HS200' in Path('/sys/kernel/debug/mmc0/ios').read_text()
    assert int((param/'fault').read_text())==0 and int((param/'actual_hz').read_text())==100000000
    for i,n in enumerate((0,4)):
        p=Path('/sys/devices/system/cpu/cpufreq')/f'policy{n}'
        assert (p/'scaling_driver').read_text().strip()=='tzx-a523-dvfs2'
        maximum[i]=max(maximum[i],int((p/'scaling_cur_freq').read_text()))
    for p in Path('/sys/class/thermal').glob('thermal_zone*'):
        name=(p/'type').read_text().strip();temp=int((p/'temp').read_text())
        assert 0<temp<80000,(name,temp)
        peaks[name]=max(peaks.get(name,0),temp)
    assert Path('/sys/class/devfreq/1800000.gpu/governor').read_text().strip()=='simple_ondemand'
    assert int(Path('/sys/module/tzx_gpu_devfreq_guard/parameters/fault').read_text())==0
    gpu_rates.add(int(Path('/sys/class/devfreq/1800000.gpu/cur_freq').read_text()))
    assert irq('2010000.iommu')==0
    for name in ('screen_buffer_errors','screen_panel_errors'):
        assert int((Path('/sys/module/tzx_display/parameters')/name).read_text())==0
    assert not [s for s in subprocess.check_output(['dmesg'],text=True).splitlines() if re.search(
        r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|I/O error|EXT4-fs error',s,re.I)]
try:
    subprocess.run(['systemctl','is-active','--quiet',*units],check=True)
    sample();before_irq=irq('cedar_dev')
    video_env=dict(os.environ,**json.loads(Path('/opt/tzx-video/env.json').read_text()))
    video=folder/'concurrent.h264'
    video.write_bytes(Path('/home/debian/video-stage/1080p/test.h264').read_bytes()*5)
    commands={
      'memory':['/home/debian/memory-check-bounded','2560'],
      'storage':['python3','/home/debian/verify_emmc_hs.py','io-worker'],
      'gpu':['runuser','-u','debian','--','env','DISPLAY=:0','XAUTHORITY=/home/debian/.Xauthority','glmark2-es2','--size','640x480','--off-screen','-b',':duration=1'],
      'compute':['python3','/home/debian/verify_gpu_compute.py'],
      'video':['gst-launch-1.0','-e','-q','filesrc','location='+str(video),'!','h264parse','!','omxh264dec','disable-dma-feature=true','!','fakesink','sync=false']}
    for name,cmd in commands.items():
        stream=(folder/(name+'.log')).open('w');streams.append(stream)
        children.append((name,subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT,env=video_env if name=='video' else None)))
    while any(p.poll() is None for _,p in children):
        assert time.monotonic()-started<180
        sample();time.sleep(.5)
    assert all(p.returncode==0 for _,p in children),[(n,p.returncode) for n,p in children]
    for stream in streams:stream.close()
    texts={n:(folder/(n+'.log')).read_text() for n in commands}
    assert 'MEMORY_TEST_2560_MIB_8_THREADS_PASS' in texts['memory']
    assert len(json.loads(texts['storage']))==2
    assert 'Mali-G57 (Panfrost)' in texts['gpu'] and 'Error:' not in texts['gpu']
    assert 'MALI_G57_COMPUTE_ALL_WORDS_PASS' in texts['compute']
    assert irq('cedar_dev')-before_irq>=600
    assert maximum==[1416000,1800000],maximum
    sample()
    assert subprocess.check_output(['pgrep','-x','Xorg'],text=True).strip()==xorg
    assert not subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip()
    assert '[lz4]' in Path('/sys/block/zram0/comp_algorithm').read_text()
    assert int(Path('/sys/block/zram0/disksize').read_text())==2147483648
    record=dict(status='PASS',boot_id=boot,seconds=round(time.monotonic()-started,2),cpu_peak_khz=maximum,
        gpu_score=int(re.search(r'glmark2 Score:\s*(\d+)',texts['gpu'])[1]),
        video_hardware_irq_delta=irq('cedar_dev')-before_irq,iommu_faults=irq('2010000.iommu'),
        storage=json.loads(texts['storage']),memory=texts['memory'],temperature_peaks_mc=peaks,
        emmc_timing='HS200',emmc_hz=100000000,emmc_errors=errors,zram_bytes=2147483648,
        xorg_pid_unchanged=xorg,screen_buffer_and_panel_errors=0,gpu_rates_hz=sorted(gpu_rates),gpu_compute=texts['compute'],
        native_gpu_governor='simple_ondemand',cpu_capacity=[int(Path('/sys/devices/system/cpu/cpu%d/cpu_capacity'%n).read_text()) for n in range(8)])
    (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    Path('/var/lib/tzx/cpu-gpu-integration-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
    print('NATIVE_CPU_GPU_FULL_STACK_COEXISTENCE_PASS',json.dumps(record),flush=True)
except BaseException as error:
    (folder/'failure.json').write_text(json.dumps(dict(error=repr(error),boot_id=boot,
        elapsed_s=round(time.monotonic()-started,2),temperature_peaks_mc=peaks,
        cpu_peak_khz=maximum,gpu_rates_hz=sorted(gpu_rates)),indent=2)+'\n')
    raise
finally:
    for _,p in children:
        if p.poll() is None:p.kill();p.wait(timeout=10)
    for stream in streams:stream.close()
    (folder/'concurrent.h264').unlink(missing_ok=True)
