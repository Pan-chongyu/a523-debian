"""Derive the next rollback-capable display installer from the exercised v4 path."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
text = (root/'firmware/upgrade_screen_standby.py').read_text()
text = (text.replace('standby', 'poweron').replace('STANDBY', 'POWERON')
        .replace('screen-functions-4-poweron', 'screen-functions-5-poweron')
        .replace('screen-functions-3-doublebuffer', 'screen-functions-4-standby')
        .replace('RESTORED_V3', 'RESTORED_V4').replace('boot-qualified v3', 'boot-qualified v4'))
text = text.replace("assert set(manifest['files']) == set(state['files']) and len(state['files']) == 7",
                    "assert set(state['files']) < set(manifest['files']) and len(state['files']) == 7")
text = text.replace("changed = {name for name, item in state['files'].items()\n               if item['sha256'] != manifest['files'][name]['sha256']}\n    assert changed == {'usr/local/lib/tzx-screen/tzx_display.ko', 'usr/local/lib/tzx-screen/runtime.py'}",
                    "changed = {name for name, item in manifest['files'].items()\n               if name not in state['files'] or state['files'][name]['sha256'] != item['sha256']}")
text = text.replace("manifest_data = Path('/home/debian/screen-poweron-FILES.json').read_bytes()",
                    "manifest_data = Path('/home/debian/screen-poweron-FILES.json').read_bytes()")
text = text.replace("    for name, item in before['files'].items():", """    installed = json.loads((BACKUP/'new-FILES.json').read_text())
    for name in set(installed['files']) - set(before['files']):
        (Path('/')/name).unlink(missing_ok=True)
    for name, item in before['files'].items():""")
text = text.replace("    run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')\n    BACKUP.mkdir",
                    "    for name in set(manifest['files']) - set(state['files']):\n        assert not (Path('/')/name).exists(), name\n    run('python3', '/usr/local/lib/tzx-dram-gpu/runtime.py', 'guard')\n    BACKUP.mkdir")
text = text.replace("assert proof['boot_id'] == BOOT and proof['result'] == 'PASS', name",
                    "assert proof['boot_id'] == BOOT and proof['result'] == 'PASS', name")
(root/'firmware/upgrade_screen_poweron.py').write_text(text, newline='\n')
print('SCREEN_POWERON_INSTALLER_PREPARED')
