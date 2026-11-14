"""Extend the verified screen function source with measured hardware vblank."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'build/screen-complete/source'
old = json.loads((base.parent/'SOURCE.json').read_text())
out = root/'build/screen-vblank/source'
out.mkdir(parents=True, exist_ok=False)
for name, digest in old['files'].items():
    data = (base/name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, name
    (out/name).write_bytes(data)
(out/'tzx_screen_vblank.inc').write_bytes((root/'firmware/tzx_screen_vblank.inc').read_bytes())
p = out/'tzx_drm.c'
text = p.read_text()


def replace(before, after):
    global text
    assert text.count(before) == 1, before
    text = text.replace(before, after)


replace('"screen-functions-1"', '"screen-functions-2-vblank"')
replace('module_param_string(screen_revision, screen_revision, sizeof(screen_revision), 0444);',
        'module_param_string(screen_revision, screen_revision, sizeof(screen_revision), 0444);\n'
        '#include "tzx_screen_vblank.inc"')
replace('    copy_frame(plane);\n    tzx_panel_blank(false);',
        '    copy_frame(plane);\n    drm_crtc_vblank_on(&pipe->crtc);\n    tzx_panel_blank(false);')
replace('    copy_frame(pipe->plane.state);\n}',
        '    copy_frame(pipe->plane.state);\n    screen_send_event(pipe);\n}')
replace('''{
    mutex_lock(&display->update_lock);
    memset(fb, 0, FB_BYTES); dma_wmb();
    mutex_unlock(&display->update_lock);
    tzx_panel_blank(true);
}''', '''{
    drm_crtc_vblank_off(&pipe->crtc);
    tzx_panel_blank(true);
    mutex_lock(&display->update_lock);
    memset(fb, 0, FB_BYTES); dma_wmb();
    mutex_unlock(&display->update_lock);
}''')
replace('    .update = pipe_update,',
        '    .update = pipe_update,\n    .enable_vblank = screen_enable_vblank,\n'
        '    .disable_vblank = screen_disable_vblank,')
replace('    /* devm releases DRM resources when the DE platform device unregisters. */',
        '    screen_vblank_cleanup();\n'
        '    /* devm releases DRM resources when the DE platform device unregisters. */')
replace('    drm_mode_config_reset(drm);',
        '    ret = screen_vblank_init(drm); if (ret) goto fail;\n    drm_mode_config_reset(drm);')
replace('.major = 1, .minor = 4,', '.major = 1, .minor = 5,')
p.write_text(text, newline='\n')
record = {'base_files': old['files'], 'hardware_qualified': False,
          'measured_frame_source': 'DSI1 VIDEO_VBLK, GIC SPI95, 252 events in 4 seconds',
          'changes': ['DRM vblank counter and events', 'DPMS vblank lifetime', 'blank before clearing pixels'],
          'unchanged': ['DMA32/PRIME/shadow scanout', 'PHY and timings', 'panel voltages'],
          'files': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir())}}
(out.parent/'SOURCE.json').write_text(json.dumps(record, indent=2)+'\n', newline='\n')
print('SCREEN_HARDWARE_VBLANK_SOURCE_PREPARED')
