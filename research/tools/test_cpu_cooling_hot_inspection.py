"""Regression: valid hot-zone readings must not reject an active cooling policy."""
import ast
import json
from pathlib import Path
import tempfile

root = Path(__file__).resolve().parents[1]


def inspect(source, temperature):
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'inspect')
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)

        def path(name):
            return fixture/name.lstrip('/')

        def write(name, value):
            target = path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(value))

        policies = []
        for cpu in (0, 4):
            name = f'/sys/devices/system/cpu/cpufreq/policy{cpu}'
            policies.append(path(name))
            for key, value in {'scaling_driver': 'tzx-a523-divider', 'scaling_governor': 'schedutil',
                               'scaling_max_freq': 120000}.items():
                write(name+'/'+key, value)
        names = ('cpu-big-thermal', 'cpu-little-thermal', 'gpu-thermal', 'npu-thermal',
                 'ddr-thermal', 'tzx-board-thermal')
        for index, name in enumerate(names):
            zone = f'/sys/class/thermal/thermal_zone{index}'
            write(zone+'/type', name)
            write(zone+'/temp', temperature)
            if name == 'tzx-board-thermal':
                write(zone+'/policy', 'step_wise')
                for trip, value in enumerate((70000, 80000, 95000)):
                    write(zone+f'/trip_point_{trip}_temp', value)
                for mapping in range(4):
                    write(zone+f'/cdev{mapping}_trip_point', mapping//2)
        for index in range(2):
            cdev = f'/sys/class/thermal/cooling_device{index}'
            write(cdev+'/type', f'tzx-cpu-cluster{index}')
            write(cdev+'/cur_state', 2)
        write('/sys/module/tzx_cpu_cooling/parameters/first_trip', 70000)
        write('/sys/module/tzx_cpu_cooling/parameters/second_trip', 80000)
        write('/proc/sys/kernel/random/boot_id', 'fixture-not-hardware')
        namespace = {'Path': path, 'policies': policies}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        return namespace['inspect']()


old = root/'build/cpu-cooling-v1/tzx_cpu_cooling_runtime.py'
new = root/'firmware/tzx_cpu_cooling_runtime.py'
try:
    inspect(old, 82000)
except AssertionError:
    pass
else:
    raise AssertionError('Regression fixture failed to reproduce the old hot-reading rejection')
for value in (74000, 82000):
    result = inspect(new, value)
    assert set(result['temperatures_mC'].values()) == {value}
    assert result['cpu_maximum_kHz'] == [120000, 120000]
for invalid in (0, 126000):
    try:
        inspect(new, invalid)
    except AssertionError:
        continue
    raise AssertionError('Invalid sensor reading accepted')
record = {'result': 'PASS', 'old_82C_rejection_reproduced': True,
          'new_valid_temperatures_mC': [74000, 82000], 'invalid_temperatures_rejected_mC': [0, 126000],
          'scope': 'runtime inspect function against synthetic sysfs; not a heated hardware test'}
(root/'evidence/cpu-cooling-v2-hot-inspection-regression.json').write_text(json.dumps(record, indent=2)+'\n')
print('CPU_COOLING_HOT_INSPECTION_REGRESSION_PASS', json.dumps(record))
