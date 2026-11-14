"""Freeze a low-physical-address placement variant; preserve the v8 workload."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
out = root/'build/cpu-copy-low-v9'
out.mkdir(exist_ok=True)
assert not (out/'BUILD_COMPLETE.json').exists()
source = (root/'build/cpu-copy-v8/library_copy_coherency.c').read_text()
assert hashlib.sha256((root/'build/cpu-copy-v8/library_copy_coherency.c').read_bytes()).hexdigest() == 'c50955b1ad74d9dd5bd905f598651ae6aa934108dfef1fb52cd6aea610ec99e3'
source = source.replace('>= (1ULL<<20)', '< (1ULL<<20)')
source = source.replace('physical(targets[cpu]+off) < (1ULL<<32)', 'physical(targets[cpu]+off) >= (1ULL<<32)')
source = source.replace('TZX_COPY_HIGH_TARGETS', 'TZX_COPY_LOW_TARGETS')
source = source.replace('HIGH_POOL', 'LOW_POOL').replace('high_pool_pages', 'low_pool_pages')
source = source.replace('selected_page_moved_low', 'selected_page_moved_high')
source = source.replace('high-address selection pool', 'low-address selection pool')
path = out/'library_copy_coherency.c'
path.write_text(source, encoding='utf8', newline='\n')
binary = out/'library-copy-low-v9'
with (out/'build.log').open('w') as log:
    subprocess.run(['aarch64-linux-gnu-gcc','-O2','-static','-pthread','-Wall','-Wextra',
        '-Wconversion','-Werror','-fno-builtin-memcpy','-fno-builtin-memcmp',
        '-o', str(binary), str(path)],check=True,stdout=log,stderr=subprocess.STDOUT)
record = {'based_on': 'cpu-copy-v8', 'changed_only': 'physical target selection below 4GiB',
    'dedicated_reference_mprotect_readonly': True, 'physical_page_snapshots': True,
    'files': {p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
              for p in (binary,path)}}
(out/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print('LOW_COPY_BUILT',json.dumps(record),flush=True)
