"""Freeze the read-only-reference and full-PFN diagnostic in WSL."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
out = root/'build/cpu-copy-v8'
out.mkdir(exist_ok=True)
assert not (out/'BUILD_COMPLETE.json').exists()
source = out/'library_copy_coherency.c'
shutil.copy2(root/'firmware/library_copy_coherency.c', source)
binary = out/'library-copy-coherency-v8'
with (out/'build.log').open('w') as log:
    subprocess.run(['aarch64-linux-gnu-gcc', '-O2', '-static', '-pthread', '-Wall', '-Wextra',
        '-Wconversion', '-Werror', '-fno-builtin-memcpy', '-fno-builtin-memcmp',
        '-o', str(binary), str(source)], check=True, stdout=log, stderr=subprocess.STDOUT)
record = {'selection_pool_mib':2816, 'headroom_mib':512,
    'dedicated_reference_mprotect_readonly': True, 'physical_page_snapshots': True,
    'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in (binary,source)}}
(out/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
