"""Prepare a separate display revision from the qualified DMA32 source."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root/'build/gpu-dma32-aarch64/display-source'
out = root/'build/screen-complete/source'
out.mkdir(parents=True, exist_ok=False)
pins = {
    'tzx_drm.c': '35df4143050a4879bca22726b03d025a10358092255c14630ea227577a848625',
    'tzx_de_scanout.c': '8f021a0875ad0a82cca7a379c8f49dc14400515c171097436812eb63ecf93143',
    'tzx_dsi_probe.c': '0a0250dd5ff78120e1774ab7004d7218cf438d7e29efff473a72083231d62287',
    'tzx_dsi_phy.h': 'f5bb1e1394c52dff644fd45e1b18938d73981dc4487bb8e0d50f7471f1b2dad2',
    'tzx_dsi_video.h': 'a6ada52765e064f6169fc8d907bf8645c8759202c9c2e6f9f7601b81ff4b6aa2',
}
for name, digest in pins.items():
    data = (base/name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, name
    (out/name).write_bytes(data)


def replace(name, old, new):
    path = out/name
    data = path.read_text()
    assert data.count(old) == 1, (name, old)
    path.write_text(data.replace(old, new), newline='\n')


replace('tzx_drm.c',
        'drm->mode_config.min_width = WIDTH; drm->mode_config.max_width = WIDTH;\n'
        '    drm->mode_config.min_height = HEIGHT; drm->mode_config.max_height = HEIGHT;',
        '/* Xorg rotates in a 1280x800 render buffer; panel timing stays fixed. */\n'
        '    drm->mode_config.min_width = WIDTH; drm->mode_config.max_width = HEIGHT;\n'
        '    drm->mode_config.min_height = WIDTH; drm->mode_config.max_height = HEIGHT;')
replace('tzx_drm.c', '.major = 1, .minor = 3,', '.major = 1, .minor = 4,')
replace('tzx_drm.c', 'static bool panel_started, hardware_started, drm_registered;',
        'static bool panel_started, hardware_started, drm_registered;\n'
        'static char screen_revision[] = "screen-functions-1";\n'
        'module_param_string(screen_revision, screen_revision, sizeof(screen_revision), 0444);')
replace('tzx_dsi_probe.c',
        'static const struct backlight_ops panel_backlight_ops = {\n'
        '    .options = BL_CORE_SUSPENDRESUME, .update_status = panel_brightness,\n};',
        '''/* Report actual PWM output, including DPMS blanking, instead of the
 * requested brightness. The backlight core serializes update_status calls. */
static int panel_actual_brightness(struct backlight_device *device)
{
    if (!(readl(pwm + 0x80) & BIT(0))) return 0;
    return min_t(unsigned int, 100,
                 DIV_ROUND_CLOSEST((readl(pwm + 0x104) & 0xffff) * 100, 480));
}
static const struct backlight_ops panel_backlight_ops = {
    .options = BL_CORE_SUSPENDRESUME, .update_status = panel_brightness,
    .get_brightness = panel_actual_brightness,
};''')
replace('tzx_dsi_probe.c',
        '.type = BACKLIGHT_RAW, .max_brightness = 100, .brightness = 20,',
        '.type = BACKLIGHT_RAW, .max_brightness = 100, .brightness = 20,\n'
        '        .power = BACKLIGHT_POWER_OFF,')
replace('tzx_dsi_probe.c',
        '        release_probe(); return ret;\n    }\n    return 0;\n}\nvoid tzx_panel_exit(void)',
        '        release_probe(); return ret;\n    }\n'
        '    /* Light the glass only after DRM has copied its first frame. */\n'
        '    backlight_update_status(panel_backlight);\n'
        '    return 0;\n}\nvoid tzx_panel_exit(void)')
replace('tzx_dsi_probe.c',
        'if (panel_backlight) { backlight_device_unregister(panel_backlight); panel_backlight = NULL; }',
        'if (panel_backlight) {\n'
        '        backlight_disable(panel_backlight);\n'
        '        backlight_device_unregister(panel_backlight); panel_backlight = NULL;\n    }')
record = {'base': pins,
          'changes': ['1280x800 desktop rotation buffer', 'actual PWM brightness including DPMS',
                      'backlight dark until first DRM frame and during exit'],
          'unchanged': ['panel timings', 'PHY analog/PLL', 'PMIC voltages', 'GPU PRIME cache and DMA32'],
          'hardware_qualified': False,
          'files': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir())}}
(out.parent/'SOURCE.json').write_text(json.dumps(record, indent=2)+'\n', newline='\n')
print('SCREEN_CANDIDATE_PREPARED', json.dumps(record))
