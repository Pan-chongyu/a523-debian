"""Prepare a separate power-on/landscape build from the qualified standby source."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'build/screen-standby'
out = root/'build/screen-poweron/source'
out.mkdir(parents=True, exist_ok=False)
source = json.loads((base/'SOURCE.json').read_text())
for name, digest in source['files'].items():
    data = (base/'source'/name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, name
    (out/name).write_bytes(data)


def edit(name, old, new):
    path = out/name
    text = path.read_text()
    assert text.count(old) == 1, (name, old)
    path.write_text(text.replace(old, new), newline='\n')


edit('tzx_drm.c', 'screen-functions-4-standby', 'screen-functions-5-poweron')
edit('tzx_drm.c', 'extern void tzx_panel_blank(bool blank);',
     'extern void tzx_panel_blank(bool blank);\nextern void tzx_panel_frame_ready(void);')
edit('tzx_drm.c', 'static void copy_frame(struct drm_plane_state *state)',
     'static int copy_frame(struct drm_plane_state *state)')
edit('tzx_drm.c', '    if (!frame || screen_panel_sleeping) return;',
     '    if (!frame || screen_panel_sleeping) return -EPIPE;')
edit('tzx_drm.c', 'if (drm_WARN_ON_ONCE(&display->drm, iosys_map_is_null(&shadow->data[0]))) return;',
     'if (drm_WARN_ON_ONCE(&display->drm, iosys_map_is_null(&shadow->data[0]))) return -EINVAL;')
edit('tzx_drm.c', 'if (ret) { dma_buf_put(dmabuf); return; }',
     'if (ret) { dma_buf_put(dmabuf); return ret; }')
edit('tzx_drm.c', '    if (!destination) goto unlock;',
     '    if (!destination) { ret = -EIO; goto unlock; }')
edit('tzx_drm.c', '    screen_commit_back_buffer();', '    ret = screen_commit_back_buffer();')
edit('tzx_drm.c', '        dma_buf_put(dmabuf);\n    }\n}\nstatic void pipe_enable',
     '        dma_buf_put(dmabuf);\n    }\n    return ret;\n}\nstatic void pipe_enable')
edit('tzx_drm.c', '    copy_frame(plane);\n    drm_crtc_vblank_on(&pipe->crtc);\n    tzx_panel_blank(false);',
     '''    if (copy_frame(plane)) {
        tzx_panel_blank(true);
        drm_err(&display->drm, "first frame failed; backlight remains off\\n");
        return;
    }
    /* RCQ FINISH and active-address readback have completed. Never expose
     * TCON's temporary pattern or an uncommitted framebuffer on the glass. */
    tzx_panel_frame_ready();
    drm_crtc_vblank_on(&pipe->crtc);
    tzx_panel_blank(false);''')
edit('tzx_drm.c', '    display->connector.status = connector_status_connected;',
     '''    display->connector.status = connector_status_connected;
    /* Software fbcon uses this before its first rendering; Xorg receives the
     * same immutable mounting hint. Native DSI timing remains 800x1280. */
    ret = drm_connector_set_panel_orientation(&display->connector,
                                              DRM_MODE_PANEL_ORIENTATION_RIGHT_UP);
    if (ret) goto fail;''')
edit('tzx_drm.c', '.major = 1, .minor = 7,', '.major = 1, .minor = 8,')

edit('tzx_dsi_probe.c', 'static void release_probe(void);', '''static void release_probe(void);
#ifdef TZX_PANEL_COMPONENT
static bool panel_frame_committed;
static unsigned int panel_power_phase;
static int panel_power_status = -1;
static unsigned long panel_backlight_blocked;
module_param(panel_frame_committed, bool, 0444);
module_param(panel_power_phase, uint, 0444);
module_param(panel_power_status, int, 0444);
module_param(panel_backlight_blocked, ulong, 0444);
#endif''')
edit('tzx_dsi_probe.c', '    writel(BIT(0), pwm + 0x80);', '''#ifdef TZX_PANEL_COMPONENT
    /* PWM is prepared with the output disabled. DRM enables it only after
     * a complete first-frame RCQ transaction and address readback. */
    writel(0, pwm + 0x80);
#else
    writel(BIT(0), pwm + 0x80);
#endif''')
edit('tzx_dsi_probe.c', '    pins_saved = true;\n    gpiod_add_lookup_table(&pins); lookup = true;',
     '''    pins_saved = true;
    gpiod_add_lookup_table(&pins); lookup = true;
#ifdef TZX_PANEL_COMPONENT
    /* Hold PD23 low before either panel bias rail or reset is released. */
    bl = gpiod_get(&owner->dev, "backlight", GPIOD_ASIS);
    if (IS_ERR(bl)) { ret = PTR_ERR(bl); bl = NULL; goto out; }
    ret = gpiod_direction_output(bl, 0);
    if (ret) goto out;
    panel_power_phase = 1;
#endif''')
edit('tzx_dsi_probe.c', '        pr_info("TZX DSI: candidate panel bias enable PH18 then PH19\\n");',
     '''        pr_info("TZX DSI: panel bias PH18 then PH19, backlight held off\\n");
#ifdef TZX_PANEL_COMPONENT
        panel_power_phase = 2;
#endif''')
edit('tzx_dsi_probe.c', '    gpiod_set_value_cansleep(reset, 1);\n    msleep(120);',
     '''    gpiod_set_value_cansleep(reset, 1);
    msleep(120);
#ifdef TZX_PANEL_COMPONENT
    panel_power_phase = 3;
#endif''')
edit('tzx_dsi_probe.c', '            read_id(host, 0xdc) != 0x04) { ret = -ENODEV; goto out; }',
     '''            read_id(host, 0xdc) != 0x04) { ret = -ENODEV; goto out; }
#ifdef TZX_PANEL_COMPONENT
        panel_power_phase = 4;
#endif''')
edit('tzx_dsi_probe.c', '        for (unsigned int cmd = 0x0a; cmd <= 0x0f; cmd++) read_id(host, cmd);',
     '''        for (unsigned int cmd = 0x0a; cmd <= 0x0f; cmd++) {
            int value = read_id(host, cmd);
#ifdef TZX_PANEL_COMPONENT
            if (cmd == 0x0a) panel_power_status = value;
#endif
        }
#ifdef TZX_PANEL_COMPONENT
        if (panel_power_status < 0 || !(panel_power_status & BIT(4))) {
            ret = -EIO; goto out;
        }
        panel_power_phase = 5;
#endif''')
edit('tzx_dsi_probe.c', '        start_video();', '''        start_video();
#ifdef TZX_PANEL_COMPONENT
        panel_power_phase = 6;
#endif''')
edit('tzx_dsi_probe.c', '        bl = gpiod_get(&owner->dev, "backlight", GPIOD_ASIS);\n        if (IS_ERR(bl)) { ret = PTR_ERR(bl); bl = NULL; goto out; }',
     '''        if (!bl) {
            bl = gpiod_get(&owner->dev, "backlight", GPIOD_ASIS);
            if (IS_ERR(bl)) { ret = PTR_ERR(bl); bl = NULL; goto out; }
        }''')
edit('tzx_dsi_probe.c', '    release_video();\n    if (pwm_saved) {',
     '''    /* Blank before stopping the video clocks during errors and shutdown. */
    if (pwm_saved) writel(0, pwm + 0x80);
    if (bl) gpiod_set_value_cansleep(bl, 0);
    release_video();
    if (pwm_saved) {''')
edit('tzx_dsi_probe.c', '    unsigned int brightness = backlight_get_brightness(device);',
     '''    unsigned int brightness = backlight_get_brightness(device);
    if (brightness && !panel_frame_committed) {
        panel_backlight_blocked++;
        brightness = 0;
    }
    if (brightness) panel_power_phase = 8;''')
edit('tzx_dsi_probe.c', 'void tzx_panel_blank(bool blank)\n{', '''void tzx_panel_frame_ready(void)
{
    panel_frame_committed = true;
    panel_power_phase = 7;
    pr_info("TZX PANEL: first frame committed; backlight release permitted\\n");
}
void tzx_panel_blank(bool blank)
{''')
edit('tzx_dsi_probe.c', 'void tzx_panel_blank(bool blank);',
     'void tzx_panel_blank(bool blank);\nvoid tzx_panel_frame_ready(void);')
edit('tzx_dsi_probe.c', '    if (blank) backlight_disable(panel_backlight);',
     '    if (blank) { panel_frame_committed = false; backlight_disable(panel_backlight); }')
record = {'hardware_qualified': False, 'base_profile': 'screen-functions-4-standby',
          'changes': ['PD23 held low before panel bias/reset', 'PWM disabled until successful RCQ first frame',
                      'validate panel awake status', 'DRM right-up mounting hint before fbdev setup'],
          'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}}
(out.parent/'SOURCE.json').write_text(json.dumps(record, indent=2)+'\n')
print('SCREEN_POWERON_SOURCE_PREPARED')
