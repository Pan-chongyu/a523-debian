"""Freeze power-on ordering, default landscape and actual new-kernel boot evidence."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root/'build/screen-poweron'
manifest = json.loads((out/'FILES.json').read_text())
source = json.loads((out/'SOURCE.json').read_text())
for name, digest in source['files'].items():
    assert hashlib.sha256((out/'source'/name).read_bytes()).hexdigest() == digest, name
assert hashlib.sha256((out/'tzx_display.ko').read_bytes()).hexdigest() == manifest['files']['usr/local/lib/tzx-screen/tzx_display.ko']['sha256']
assert hashlib.sha256((out/'screen-runtime-poweron.tar.gz').read_bytes()).hexdigest() == manifest['package_sha256']
observer = json.loads((root/'evidence/screen-poweron-kernel-boot-watch.json').read_text())
assert observer['state'] == 'SSH_READY' and observer['linux_boot_id'] == 'adf71c15-fdfb-449f-a30d-854879e00fa3'
required = {
    'screen-poweron-manual-final.txt': ['TZX_SCREEN_POWERON_AND_RIGHT_LANDSCAPE_PASS', 'TZX_SCREEN_KMS_PAGEFLIP_EVENTS_PASS'],
    'screen-poweron-boot-verified.txt': ['SCREEN_BOOT_KERNEL_ACTUAL_BOOT_ROTATED_CONSOLE_PASS',
                                      'TZX_SCREEN_ACTUAL_REBOOT_BRIGHTNESS_ROTATION_TOUCH_GPU_PASS'],
    'screen-poweron-postboot-complete.txt': ['TZX_SCREEN_HARDWARE_DRM_VBLANK_DPMS_PASS',
        'TZX_SCREEN_DCS_SLEEP_VIDEO_STOP_AND_WAKE_PASS', 'TZX_SCREEN_FOUR_ORIENTATIONS_AND_TOUCH_MATRIX_PASS',
        'TZX_SCREEN_BACKLIGHT_DPMS_TEST_PASS', 'TZX_SCREEN_DUAL_DMA_RCQ_ADDRESS_ANIMATION_PASS',
        'TZX_SCREEN_CONCURRENT_SETTINGS_PASS', 'TZX_SCREEN_KMS_PAGEFLIP_EVENTS_PASS',
        'TZX_SCREEN_POWERON_AND_RIGHT_LANDSCAPE_PASS', 'GPU_CLOCKFIX_FULL_SCENE_PASSES_1',
        'GPU_FULL_X11_WITH_1_SCENES_AND_THREE_512MIB_CPU_MEMORY_PASSES'],
    'screen-poweron-final-file-audit.txt': ['MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS',
                                         'ActiveState=inactive', 'Result=success', 'ExecMainStatus=0'],
}
evidence = {}
for name, markers in required.items():
    data = (root/'evidence'/name).read_bytes()
    text = data.decode('utf8')
    assert all(marker in text for marker in markers) and 'Traceback' not in text, name
    evidence['evidence/'+name] = hashlib.sha256(data).hexdigest()
kernel = json.loads((root/'build/screen-boot-kernel/linux-bundle.json').read_text())
record = {'revision': 'screen-functions-5-poweron', 'qualification': 'bounded hardware tests and actual eMMC boot',
          'manual_boot_id': '11b34063-864c-4db8-887b-82e4404dd87f',
          'actual_autostart_boot_id': observer['linux_boot_id'], 'package_sha256': manifest['package_sha256'],
          'module_sha256': manifest['files']['usr/local/lib/tzx-screen/tzx_display.ko']['sha256'],
          'kernel_bundle': kernel, 'original_exported_symbol_CRCs_unchanged': 9248,
          'default_orientation': {'fbcon': 'clockwise, rotate=1, 160x50',
                                  'initial_Xorg': '1280x800 right', 'before_greeter': '1280x800 right',
                                  'every_new_desktop_session': 'right',
                                  'touch_matrix': [0, 1, 0, -1, 0, 1, 0, 0, 1]},
          'poweron_sequence': ['backlight GPIO low', 'bias and reset', 'panel ID and awake-state validation',
                               'PWM configured disabled', 'first frame copied', 'RCQ FINISH and address readback',
                               'backlight enabled'],
          'poweroff_key_on_this_revision': 'deferred at user request; keep desktop running',
          'limitations': ['panel supply/bias remain powered during DPMS', 'no full system suspend',
                          'GPIO/PWM guarded board-specific ownership', 'CPU shadow copy, no zero-copy scanout',
                          'subjective display observation and battery-disconnected power cycle not tested this revision'],
          'rollback': ['python3 /home/debian/upgrade_screen_poweron.py restore',
                       'python3 /home/debian/install_screen_boot_kernel.py restore; then reboot'],
          'evidence': evidence}
with (out/'QUALIFICATION.json').open('x', encoding='utf8') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print('SCREEN_POWERON_QUALIFICATION_FROZEN', json.dumps({'boot_id': observer['linux_boot_id'], 'evidence_files': len(evidence)}))
