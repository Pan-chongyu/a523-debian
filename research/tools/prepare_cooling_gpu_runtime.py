"""Extend only health's zone inventory for the board's new aggregate zone."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root/'firmware/tzx_dram_gpu_runtime.py').read_bytes()
assert hashlib.sha256(source).hexdigest() == '7f2a58be42766a8a6af14171d972654d6006f69179bbb87eeb67dc4216282189'
old = b"    assert len(state['temperatures_mC']) == 5 and all(0 < v < 75000 for v in state['temperatures_mC'].values())"
new = b"""    physical = {'gpu-thermal', 'cpu-big-thermal', 'cpu-little-thermal', 'npu-thermal', 'ddr-thermal'}
    observed = set(state['temperatures_mC'])
    assert physical <= observed <= physical | {'tzx-board-thermal'}
    assert all(0 < v < 75000 for v in state['temperatures_mC'].values())"""
assert source.count(old) == 1
target = source.replace(old, new)
compile(target, 'gpu-runtime-cooling.py', 'exec')
path = root/'build/cpu-cooling/gpu-runtime-cooling.py'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(target)
record = {'source_sha256': hashlib.sha256(source).hexdigest(),
          'new_sha256': hashlib.sha256(target).hexdigest(),
          'change': 'Health still requires all five physical channels; accepts only one additional named aggregate thermal zone',
          'module_and_boot_changes': False}
(path.parent/'GPU_HEALTH_PATCH.json').write_text(json.dumps(record, indent=2)+'\n')
print('COOLING_GPU_HEALTH_INVENTORY_PATCH_PREPARED', json.dumps(record))
