"""Isolate 3GiB diagnostic wrappers without relaxing the normal full-RAM gates."""
import hashlib
import json
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--memory-mib',type=int,choices=(1792,1920),default=1920)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
out = root/('build/k5-low-window-3g/runtime' if args.memory_mib == 1920 else 'build/k5-low-window-3g/runtime-1792')
out.mkdir()
sources = {}
loader = (root/'firmware/start_gpu_dma32_trial.py').read_text()
guard = "assert int(next(row.split()[1] for row in Path('/proc/meminfo').read_text().splitlines()\n                if row.startswith('MemTotal:'))) > 3900000"
assert loader.count(guard) == 1
loader = loader.replace(guard,"""assert struct.unpack('>4I',Path('/sys/firmware/devicetree/base/memory@40000000/reg').read_bytes()) == (0,0x40000000,0,0xc0000000)
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256'] == '0d9c3e238b5910f299c24d9c09d2a759e06076756150f5560a0f8af3148da985'
assert 3000000 < int(next(row.split()[1] for row in Path('/proc/meminfo').read_text().splitlines() if row.startswith('MemTotal:'))) < 3100000""")
sources['start_gpu_low_window.py'] = loader
desktop = (root/'firmware/run_gpu_dma32_desktop_trial.py').read_text()
assert desktop.count('/home/debian/start_gpu_dma32_trial.py') == 1
assert desktop.count("'--memory-mib', '2560'") == 1
desktop = desktop.replace('/home/debian/start_gpu_dma32_trial.py','/home/debian/start_gpu_low_window.py')
desktop = desktop.replace("'--memory-mib', '2560'","'--memory-mib', '"+str(args.memory_mib)+"'")
sources['run_gpu_low_window_desktop.py'] = desktop
guarded = (root/'firmware/run_guarded_gpu_trial.py').read_text()
assert guarded.count('/home/debian/run_gpu_dma32_desktop_trial.py') == 1
guarded = guarded.replace('/home/debian/run_gpu_dma32_desktop_trial.py','/home/debian/run_gpu_low_window_desktop.py')
guarded = guarded.replace("'persistent_gpu_enablement': False}","'persistent_gpu_enablement': False, 'diagnostic_RAM_bytes': 3<<30, 'cpu_pressure_mib':"+str(args.memory_mib)+"}")
sources['run_guarded_gpu_low_window.py'] = guarded
for name,source in sources.items():
    compile(source,name,'exec')
    (out/name).write_text(source,encoding='utf8',newline='\n')
record = {'diagnostic_only':True,'normal_full_RAM_scripts_modified':False,
    'memory_pressure_mib':args.memory_mib,'remaining_SCENE_and_guard_workload_unchanged':True,
    'files':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in sources}}
(out/'MANIFEST.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print('LOW_WINDOW_GPU_WRAPPERS_PREPARED',json.dumps(record),flush=True)
