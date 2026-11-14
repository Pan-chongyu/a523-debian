import hashlib
import json
from pathlib import Path
import shutil
import subprocess
root=Path(__file__).resolve().parents[1]
out=root/'build/physical-pattern-v2'
out.mkdir(exist_ok=True)
assert not (out/'BUILD_COMPLETE.json').exists()
source=out/'physical_memory_pattern.c'
shutil.copy2(root/'firmware/physical_memory_pattern.c',source)
binary=out/'physical-memory-pattern'
with (out/'build.log').open('w') as stream:
    subprocess.run(['aarch64-linux-gnu-gcc','-O2','-static','-pthread','-Wall','-Wextra',
                    '-Wconversion','-Werror','-o',str(binary),str(source)],
                   check=True,stdout=stream,stderr=subprocess.STDOUT)
record={'pool_mib':2944,'headroom_mib':512,'pinned':True,'physical_address_pattern':True,
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,binary)}}
(out/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
