"""Derive standard DCS standby from the actual boot-qualified double-buffer build."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'build/screen-doublebuffer-r2'
qualification = json.loads((base/'QUALIFICATION.json').read_text())
assert qualification['module_sha256'] == hashlib.sha256((base/'tzx_display.ko').read_bytes()).hexdigest()
source = json.loads((base/'SOURCE.json').read_text())
out = root/'build/screen-standby/source'
out.mkdir(parents=True, exist_ok=False)
for name, digest in source['files'].items():
    data = (base/'source'/name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, name
    (out/name).write_bytes(data)
(out/'tzx_screen_standby.inc').write_bytes((root/'firmware/tzx_screen_standby.inc').read_bytes())


def edit(name, old, new):
    path = out/name
    text = path.read_text()
    assert text.count(old) == 1, (name, old)
    path.write_text(text.replace(old, new), newline='\n')


edit('tzx_drm.c', 'extern void tzx_panel_blank(bool blank);',
     'extern void tzx_panel_blank(bool blank);\nextern int tzx_panel_set_sleep(bool sleep, int *status);')
edit('tzx_drm.c', 'screen-functions-3-doublebuffer', 'screen-functions-4-standby')
edit('tzx_drm.c', '#include "tzx_screen_doublebuffer.inc"',
     '#include "tzx_screen_doublebuffer.inc"\n#include "tzx_screen_standby.inc"')
edit('tzx_drm.c', '    if (!frame) return;', '    if (!frame || screen_panel_sleeping) return;')
edit('tzx_drm.c', '    copy_frame(plane);\n    drm_crtc_vblank_on(&pipe->crtc);',
     '    if (screen_panel_resume()) return;\n    copy_frame(plane);\n    drm_crtc_vblank_on(&pipe->crtc);')
edit('tzx_drm.c', '    tzx_panel_blank(true);\n    mutex_lock(&display->update_lock);\n'
     '    memset(fb, 0, FB_BYTES);\n    memset(screen_second, 0, FB_BYTES); dma_wmb();\n'
     '    mutex_unlock(&display->update_lock);', '    screen_panel_suspend();')
edit('tzx_drm.c', '.major = 1, .minor = 6,', '.major = 1, .minor = 7,')
edit('tzx_dsi_probe.c', 'void tzx_panel_blank(bool blank);',
     'void tzx_panel_blank(bool blank);\nint tzx_panel_set_sleep(bool sleep, int *status);')
edit('tzx_dsi_probe.c', 'int __init tzx_panel_init(void)\n{', '''int tzx_panel_set_sleep(bool sleep, int *status)
{
    int ret;
    /* Caller stopped HSD at a frame boundary and holds the update mutex.
     * Retain glass-specific registers, GPIO bias and established voltages. */
    if (sleep) {
        ret = lp_packet(host, 0x05, 0x28, false); /* display off */
        if (ret) return ret;
        msleep(50);
        ret = lp_packet(host, 0x05, 0x10, false); /* sleep in */
        if (ret) return ret;
        msleep(150);
    } else {
        ret = lp_packet(host, 0x05, 0x11, false); /* sleep out */
        if (ret) return ret;
        msleep(150);
        ret = lp_packet(host, 0x05, 0x29, false); /* display on */
        if (ret) return ret;
        msleep(150);
        ret = lp_packet(host, 0x05, 0x13, false); /* normal pixel data */
        if (ret) return ret;
    }
    *status = read_id(host, 0x0a);
    return 0;
}
int __init tzx_panel_init(void)
{''')
record = {'hardware_qualified': False, 'base_qualification': qualification,
          'changes': ['standard DCS sleep/display off and wake',
                      'HSD stopped before LP commands; jump chain and HSC restored before copying',
                      'keep known rail/bias configuration; no system suspend'],
          'files': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir())}}
(out.parent/'SOURCE.json').write_text(json.dumps(record, indent=2)+'\n', newline='\n')
print('TZX_SCREEN_STANDBY_SOURCE_PREPARED')
