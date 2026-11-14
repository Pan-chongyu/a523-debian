"""Create exact full-length TOC0 guard replacements from the frozen live baseline."""
import ast
import hashlib
import json
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parents[1]
folder=root/'build/boot-panel-early-v2'
manifest=json.loads((folder/'loader.toc0.json').read_text())
assert manifest['ARM_emulation_verified'] and len(manifest['emulation'])==17
sha=lambda b:hashlib.sha256(b).hexdigest()
archive_path=root/'build/boot-performance-installed-checkpoint-v2.tar.gz'
assert sha(archive_path.read_bytes())=='fce36e72ecd274d45dc70d3e4136a6fd096bbd333bd351b9ffccc3f42a47ec7c'
helper='''def read_exact_board_toc0(fd):
    head = os.pread(fd, 32, 256*512)
    assert len(head) == 32 and head[:8] == b'TOC0.GLH'
    length = int.from_bytes(head[28:32], 'little')
    assert length in (40960, 49152)
    data = os.pread(fd, length, 256*512)
    assert len(data) == length
    return data

'''
files={}
with tarfile.open(archive_path) as archive:
    for component in ('tzx-dram-gpu','tzx-rtc-context','tzx-pmic-poweroff'):
        name='usr/local/lib/'+component+'/runtime.py'
        original=archive.extractfile(name).read()
        text=original.decode()
        needle="'"+manifest['previous_toc0_sha256']+"')"
        assert text.count(needle)==1
        text=text.replace(needle,"'"+manifest['previous_toc0_sha256']+"', '"+manifest['image_sha256']+"')")
        hits=sum(text.count(s) for s in ('os.pread(fd, 40960, 256*512)','os.pread(fd, 40960, 256 * 512)'))
        assert hits==1
        for s in ('os.pread(fd, 40960, 256*512)','os.pread(fd, 40960, 256 * 512)'):
            text=text.replace(s,'read_exact_board_toc0(fd)')
        first=next(node for node in ast.parse(text).body if not isinstance(node,(ast.Import,ast.ImportFrom))
            and not (isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)))
        index=sum(len(line) for line in text.splitlines(keepends=True)[:first.lineno-1])
        text=text[:index]+helper+text[index:]
        compile(text,name,'exec')
        target=folder/(component+'-runtime.py')
        target.write_text(text,encoding='utf-8',newline='\n')
        files['/'+name]=dict(original_sha256=sha(original),candidate_sha256=sha(target.read_bytes()),
            staged_name=target.name)
record=dict(toc0_sha256=manifest['image_sha256'],guard_files=files)
(folder/'guard-files.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('EARLY_PANEL_EXACT_LENGTH_AND_HASH_GUARDS_PREPARED',json.dumps(record),flush=True)
