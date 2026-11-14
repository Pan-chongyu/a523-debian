"""Record completed bounded phases without promoting GPU or overall stability."""
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
rows = []
for name, seconds, count, placement in (
    ('bl31-prefetch-copy-result.txt',300,47045,'all targets above 4GiB'),
    ('bl31-prefetch-natural-final.txt',300,47088,'new natural allocations, all targets above 4GiB'),
    ('bl31-prefetch-low-final.txt',120,19019,'all targets below 4GiB')):
    data = (root/'evidence'/name).read_bytes()
    text = data.decode('utf8')
    assert all(s in text for s in ('Result=success','ExecMainStatus=0','ActiveState=inactive',
        'f54b0ed6-6213-4cf1-82fe-10c608cb2cee', 'LIBRARY_FIXED_COPY_PASS', f'copies={count}'))
    assert re.search(rf'seconds_per_phase={seconds}\b',text)
    rows.append({'evidence':name,'evidence_sha256':hashlib.sha256(data).hexdigest(),
        'seconds':seconds,'copies':count,'target_placement':placement,'result':'bounded PASS'})
record = {'boot_id':'f54b0ed6-6213-4cf1-82fe-10c608cb2cee',
    'bundle_sha256':'4a6681c64fc6b173eedf6d3e28062be9596d6ea0c6c1a54b391cdb18a3fce9a9',
    'all_eight_cpuectlr':'0x28081000','cpu_clock_mhz':480,'full_4gib_retained':True,
    'added_copy_DSB':False,'phases':rows,'gpu_qualified':False,'overall_stability_qualified':False,
    'limit':'Three bounded CPU-copy phases; causality, reboot, GPU and power integration not yet qualified.'}
path = root/'build/bl31-prefetch/BOOT_AND_CPU_RESULT.json'
assert not path.exists()
path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(record,indent=2))
