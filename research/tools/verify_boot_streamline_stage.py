"""Check exact-source startup edits without executing any device operations."""
import ast
import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
baseline = json.loads((root/'evidence/boot-streamline-v3-source-input.json').read_text(encoding='utf-8'))
tree = ast.parse((root/'firmware/tzx_boot_streamline.py').read_text(encoding='utf-8'))
first = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == 'source' for target in node.targets))
last = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.Expr) and
            isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'sys.path.insert')
transform = compile(ast.Module(body=tree.body[first:last], type_ignores=[]), '<exact transforms>', 'exec')
for operation, name in dict(handoff='/usr/local/lib/tzx-boot-panel/handoff.py',
        gpu='/usr/local/lib/tzx-gpu-devfreq/startup.py',
        emmc='/usr/local/lib/tzx-emmc-hs/runtime.py').items():
    scope = dict(operation=operation, data=baseline['files'][name]['text'].encode())
    exec(transform, scope)
    compile(scope['source'], name, 'exec')
    try:
        exec(transform, dict(operation=operation, data=b'pass\n'))
    except AssertionError:
        pass
    else:
        raise AssertionError('Unexpected source template was accepted: '+operation)
with tarfile.open(root/'build/boot-streamline-stage.tar.gz') as archive:
    members = archive.getmembers()
    files = {'/'+item.name: archive.extractfile(item).read() for item in members}
    manifest = json.loads(files['/usr/local/lib/tzx-boot-streamline-v6/manifest.json'])
    assert len(files) == len(members) == 12
    for name, digest in manifest['files'].items():
        assert hashlib.sha256(files[name]).hexdigest() == digest
    assert not any('tzx-bluetooth.service' in name for name in files)
    for component in ('tzx-emmc-hs', 'tzx-performance-mode'):
        value = json.loads(files['/usr/local/lib/'+component+'/manifest.json'])
        for name, digest in value['files'].items():
            if name in files:
                assert hashlib.sha256(files[name]).hexdigest() == digest
print('EXACT_TEMPLATES_REJECT_UNKNOWN_AND_STAGE_GUARD_PINS_PASS', flush=True)
