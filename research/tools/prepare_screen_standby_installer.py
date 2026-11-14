"""Retain the exercised trial/rollback sequence for the next display revision."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
text = (root/'firmware/upgrade_screen_doublebuffer.py').read_text()
text = (text.replace('doublebuffer', 'standby').replace('DOUBLEBUFFER', 'STANDBY')
        .replace('screen-standby-r2', 'screen-standby')
        .replace('screen-functions-3-standby', 'screen-functions-4-standby')
        .replace('screen-functions-2-vblank', 'screen-functions-3-doublebuffer')
        .replace('RESTORED_V2', 'RESTORED_V3').replace('boot-qualified v2', 'boot-qualified v3'))
marker = "'screen-pageflip-test.json', 'screen-standby-test.json', 'screen-settings-concurrency.json'"
assert text.count(marker) == 1
text = text.replace(marker, "'screen-pageflip-test.json', 'screen-standby-test.json', "
                           "'screen-doublebuffer-test.json', 'screen-settings-concurrency.json'")
marker = "    assert not PENDING.exists()\n    assert not subprocess.check_output"
assert text.count(marker) == 1
text = text.replace(marker, "    assert int(Path('/sys/module/tzx_display/parameters/screen_panel_errors').read_text()) == 0\n"
                           "    assert Path('/sys/module/tzx_display/parameters/screen_panel_sleeping').read_text().strip() == 'N'\n"+marker)
with (root/'firmware/upgrade_screen_standby.py').open('x', newline='\n') as stream:
    stream.write(text.replace("'RCQ_vblank_DPMS_rotation': True,", "'RCQ_vblank_DPMS_rotation': True, 'panel_DCS_sleep': True,"))
print('STANDBY_INSTALLER_PREPARED')
