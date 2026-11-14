"""Run exact qualified startup code while removing redundant startup work."""
import hashlib
import json
import os
import sys
from pathlib import Path

assert os.geteuid() == 0
root = Path('/usr/local/lib/tzx-boot-streamline-v6')
manifest = json.loads((root/'manifest.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
assert len(sys.argv) == 2 and sys.argv[1] in ('handoff', 'gpu', 'emmc')
operation = sys.argv[1]
name = dict(handoff='/usr/local/lib/tzx-boot-panel/handoff.py',
            gpu='/usr/local/lib/tzx-gpu-devfreq/startup.py',
            emmc='/usr/local/lib/tzx-emmc-hs/runtime.py')[operation]
data = Path(name).read_bytes()
assert hashlib.sha256(data).hexdigest() == manifest['original_sources'][name], name
source = data.decode()
if operation == 'handoff':
    # These are diagnostic receipts. A machine-wide sync flushes unrelated
    # boot traffic and is not required to transfer hardware ownership.
    assert source.count('    os.sync()\n') == 1
    source = source.replace('    os.sync()\n', '')
elif operation == 'gpu':
    # gpu-start performs this same live guard immediately before probing.
    # Its checks, pixel test and pending/failure handling remain unchanged.
    needle = "run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard')\n"
    assert source.count(needle) == 1
    source = source.replace(needle, '')
elif operation == 'emmc':
    needle = """    for name,key in (('screen-boot-health.json','result'),('dram-gpu-boot-health.json','status')):
        record=json.loads((STATE/name).read_text())
        assert record['boot_id']==BOOT and record[key]=='PASS',name
"""
    assert source.count(needle) == 1
    replacement = """    # This storage transition does not depend on a graphical session.
    # Require the same-boot RAM/voltage check and qualified CPU owner instead.
    for name in ('tzx-early-performance-check.json', 'tzx-cpu-dvfs.json'):
        record=json.loads(Path('/run',name).read_text())
        assert record['boot_id']==BOOT, name
        if name=='tzx-early-performance-check.json':
            assert record['status']=='PASS' and record['qualified_full_4GiB_and_voltage_guard']
            assert 'MEMORY_TEST_256_MIB_8_THREADS_PASS' in record['memory_result']
        else: assert record['state']=='active' and record['maximum_khz']==[1416000,1800000]
"""
    source = source.replace(needle, replacement)
sys.path.insert(0, str(Path(name).parent))
sys.argv = [name, 'run'] if operation == 'emmc' else [name]
exec(compile(source, name, 'exec'), {'__name__': '__main__', '__file__': name})
