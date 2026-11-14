"""Derive a bounded RCQ double-buffer candidate from the boot-qualified vblank."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'build/screen-vblank/source'
record = json.loads((base.parent/'SOURCE.json').read_text())
qualified = json.loads((base.parent/'QUALIFICATION.json').read_text())
assert qualified['module_sha256'] == hashlib.sha256((base.parent/'tzx_display.ko').read_bytes()).hexdigest()
out = root/'build/screen-doublebuffer-r2/source'
out.mkdir(parents=True, exist_ok=False)
for name, digest in record['files'].items():
    data = (base/name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, name
    (out/name).write_bytes(data)
(out/'tzx_screen_doublebuffer.inc').write_bytes((root/'firmware/tzx_screen_doublebuffer.inc').read_bytes())


def edit(name, old, new):
    path = out/name
    text = path.read_text()
    assert text.count(old) == 1, (name, old)
    path.write_text(text.replace(old, new), newline='\n')


edit('tzx_de_scanout.c', 'static void *fb, *regs;', 'static void *fb, *regs, *screen_second;')
edit('tzx_de_scanout.c', 'static dma_addr_t fb_dma, regs_dma;',
     'static dma_addr_t fb_dma, regs_dma, screen_second_dma;')
edit('tzx_de_scanout.c', '    if (fb) dma_free_coherent(&pdev->dev, FB_ALLOC, fb, fb_dma);',
     '    if (screen_second) dma_free_coherent(&pdev->dev, FB_ALLOC, screen_second, screen_second_dma);\n'
     '    if (fb) dma_free_coherent(&pdev->dev, FB_ALLOC, fb, fb_dma);')
edit('tzx_de_scanout.c', '    if (!fb || !regs) { ret = -ENOMEM; goto fail; }',
     '    screen_second = dma_alloc_coherent(&pdev->dev, FB_ALLOC, &screen_second_dma, GFP_KERNEL);\n'
     '    if (!fb || !regs || !screen_second) { ret = -ENOMEM; goto fail; }')
edit('tzx_drm.c', 'screen-functions-2-vblank', 'screen-functions-3-doublebuffer')
edit('tzx_drm.c', '#include "tzx_screen_vblank.inc"',
     '#include "tzx_screen_vblank.inc"\n#include "tzx_screen_doublebuffer.inc"')
edit('tzx_drm.c', '    int ret;\n    if (!frame) return;',
     '    int ret;\n    void *destination;\n    if (!frame) return;')
edit('tzx_drm.c', '    mutex_lock(&display->update_lock);\n    for (unsigned int row = 0; row < HEIGHT; row++)',
     '    mutex_lock(&display->update_lock);\n    destination = screen_back_buffer();\n'
     '    if (!destination) goto unlock;\n    for (unsigned int row = 0; row < HEIGHT; row++)')
edit('tzx_drm.c', 'iosys_map_memcpy_from(fb + row * WIDTH * 4,',
     'iosys_map_memcpy_from(destination + row * WIDTH * 4,')
edit('tzx_drm.c', '    dma_wmb();\n    mutex_unlock(&display->update_lock);',
     '    dma_wmb();\n    screen_commit_back_buffer();\nunlock:\n    mutex_unlock(&display->update_lock);')
edit('tzx_drm.c', '    memset(fb, 0, FB_BYTES); dma_wmb();',
     '    memset(fb, 0, FB_BYTES);\n    memset(screen_second, 0, FB_BYTES); dma_wmb();')
edit('tzx_drm.c', '.major = 1, .minor = 5,', '.major = 1, .minor = 6,')
edit('tzx_drm.c', '    copy_frame(pipe->plane.state);\n    screen_send_event(pipe);',
     '    int held = drm_crtc_vblank_get(&pipe->crtc);\n    copy_frame(pipe->plane.state);\n'
     '    screen_send_event(pipe);\n    if (!held) drm_crtc_vblank_put(&pipe->crtc);')
edit('tzx_screen_vblank.inc', '    int ret;\n    if (!event) return;\n    ret = drm_crtc_vblank_get(crtc);',
     '    if (!event) return;')
edit('tzx_screen_vblank.inc', '    if (ret) drm_crtc_send_vblank_event(crtc, event);\n'
     '    else drm_crtc_arm_vblank_event(crtc, event);',
     '    /* RCQ FINISH already confirmed the address latch. Report that frame,\n'
     '     * without delaying completion by another whole refresh interval. */\n'
     '    drm_crtc_send_vblank_event(crtc, event);')
record = {'hardware_qualified': False, 'base_qualification': qualified,
          'changes': ['two permanent coherent DMA32 scanout buffers',
                      'RCQ low/high address latch with FINISH and readback',
                      'freeze updates instead of reusing an uncertain scanout buffer'],
          'files': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir())}}
(out.parent/'SOURCE.json').write_text(json.dumps(record, indent=2)+'\n', newline='\n')
print('SCREEN_DOUBLEBUFFER_SOURCE_PREPARED')
