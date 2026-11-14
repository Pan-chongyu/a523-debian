"""Package independently qualified CPU/GPU supervisors with pinned manifests."""
import hashlib,io,json,tarfile
from pathlib import Path
r=Path(__file__).resolve().parents[1]
files={}
gpu='usr/local/lib/tzx-gpu-devfreq/'
for source,target in [
 ('firmware/tzx_gpu_devfreq_common.py','common.py'),
 ('firmware/tzx_gpu_devfreq_startup.py','startup.py'),
 ('firmware/tzx_gpu_devfreq_runtime.py','runtime.py'),
 ('firmware/tzx_gpu_devfreq_cleanup.py','cleanup.py'),
 ('firmware/tzx_gpu_devfreq_fallback.py','fallback.py'),
 ('build/gpu-devfreq/tzx_gpu_devfreq_opps.ko','tzx_gpu_devfreq_opps.ko'),
 ('build/gpu-devfreq/tzx_gpu_devfreq_guard.ko','tzx_gpu_devfreq_guard.ko')]:
    files[gpu+target]=(r/source).read_bytes()
gpu_start='etc/systemd/system/tzx-gpu.service.d/97-native-devfreq.conf'
files[gpu_start]=b'''[Unit]
Description=TZX Mali-G57 Panfrost with native 150-600MHz devfreq
ConditionPathExists=/var/lib/tzx/gpu-devfreq-qualified.json
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -u /usr/local/lib/tzx-gpu-devfreq/startup.py
TimeoutStartSec=80
'''
gpu_perf='etc/systemd/system/tzx-gpu-performance.service.d/97-native-devfreq.conf'
files[gpu_perf]=b'''[Unit]
Description=TZX native GPU governor with kernel thermal and leased QoS ceiling
ConditionPathExists=
ConditionPathExists=/var/lib/tzx/gpu-devfreq-qualified.json
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -u /usr/local/lib/tzx-gpu-devfreq/runtime.py
ExecStopPost=
ExecStopPost=/usr/bin/python3 -u /usr/local/lib/tzx-gpu-devfreq/cleanup.py
'''
gpu_fallback='etc/systemd/system/tzx-dram-gpu-fallback.service.d/97-native-devfreq.conf'
files[gpu_fallback]=b'''[Service]
ExecStart=
ExecStart=/usr/bin/python3 -u /usr/local/lib/tzx-gpu-devfreq/fallback.py
TimeoutStartSec=120
'''
cpu='usr/local/lib/tzx-cpu-full/'
for source,target in [('firmware/tzx_cpu_full_runtime.py','runtime.py'),
 ('build/cpu-full/tzx_cpufreq_dvfs_v2.ko','tzx_cpufreq_dvfs_v2.ko'),
 ('build/cpu-full/tzx_cpu_dvfs_cooling_v2.ko','tzx_cpu_dvfs_cooling_v2.ko')]:
    files[cpu+target]=(r/source).read_bytes()
cpu_unit='etc/systemd/system/tzx-cpu-dvfs.service.d/97-vf0300-full.conf'
files[cpu_unit]=b'''[Unit]
Description=TZX vf0300 CPU 1416/1800MHz with DCDC1 DVFS and native capacity
ConditionPathExists=
ConditionPathExists=/var/lib/tzx/cpu-full-qualified.json
ConditionPathExists=/var/lib/tzx/gpu-qualified
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -u /usr/local/lib/tzx-cpu-full/runtime.py run
ExecStopPost=
ExecStopPost=/usr/bin/python3 -u /usr/local/lib/tzx-cpu-full/runtime.py restore
'''
for prefix,owned,profile in [(gpu,[gpu_start,gpu_perf,gpu_fallback],'Panfrost-native-150-600MHz-fixed-900mV'),
                           (cpu,[cpu_unit],'vf0300-little1416-big1800-native-capacity')]:
    manifest=dict(profile=profile,files={'/'+name:hashlib.sha256(data).hexdigest() for name,data in files.items() if name.startswith(prefix) or name in owned},
        kernel_image_sha256=json.loads((r/'build/cpu-gpu-kernel/linux-bundle.json').read_text())['items'][0]['sha256'])
    files[prefix+'manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
out=r/'build/cpu-gpu-runtime.tar.gz'
with tarfile.open(out,'w:gz') as archive:
    for name,data in files.items():
        item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o644
        archive.addfile(item,io.BytesIO(data))
print('CPU_GPU_RUNTIME_PACKAGE',len(files),out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
