"""Record the bounded manual and actual boot proofs without altering build inputs."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root/'build/screen-doublebuffer-r2'
manifest = json.loads((folder/'screen-runtime-doublebuffer-settings-FILES.json').read_text())
assert manifest['files']['usr/local/lib/tzx-screen/tzx_display.ko']['sha256'] == hashlib.sha256((folder/'tzx_display.ko').read_bytes()).hexdigest()
observer = json.loads((root/'evidence/screen-doublebuffer-actual-reboot-observer.json').read_text())
assert observer['state'] == 'SSH_READY'
required = {
    'screen-doublebuffer-pageflip.txt': 'TZX_SCREEN_KMS_PAGEFLIP_EVENTS_PASS',
    'screen-doublebuffer-r2-gpu-ram.txt': 'GPU_FULL_X11_WITH_1_SCENES_AND_THREE_512MIB_CPU_MEMORY_PASSES',
    'screen-settings-save-fixed-validation.txt': 'TZX_SCREEN_FOUR_ORIENTATIONS_AND_TOUCH_MATRIX_PASS',
    'screen-doublebuffer-actual-boot-validation.txt': 'TZX_SCREEN_DUAL_DMA_RCQ_ADDRESS_ANIMATION_PASS',
    'screen-doublebuffer-postboot-settings-and-audit.txt': 'TZX_SCREEN_CONCURRENT_SETTINGS_PASS',
}
evidence = {}
for name, marker in required.items():
    data = (root/'evidence'/name).read_bytes()
    text = data.decode('utf8')
    assert marker in text and 'Traceback' not in text, name
    evidence['evidence/'+name] = hashlib.sha256(data).hexdigest()
boot_text = (root/'evidence/screen-doublebuffer-actual-boot-validation.txt').read_text(encoding='utf8')
assert observer['linux_boot_id'] in boot_text
for marker in ('TZX_SCREEN_ACTUAL_REBOOT_BRIGHTNESS_ROTATION_TOUCH_GPU_PASS',
               'TZX_SCREEN_HARDWARE_DRM_VBLANK_DPMS_PASS', 'TZX_SCREEN_BACKLIGHT_DPMS_TEST_PASS',
               'TZX_SCREEN_KMS_PAGEFLIP_EVENTS_PASS', 'CPU_COOLING_STANDARD_THERMAL_QOS_AUTOSTART_PASS',
               'CODEC_RATE_VERIFY_BOOT_PASS'):
    assert marker in boot_text, marker
record = {'revision': 'screen-functions-3-doublebuffer', 'hardware_qualified': 'bounded_hardware_tests',
          'manual_boot_id': '32e94a2b-548f-462e-bed0-47db5fe517bd',
          'actual_autostart_boot_id': observer['linux_boot_id'],
          'module_sha256': manifest['files']['usr/local/lib/tzx-screen/tzx_display.ko']['sha256'],
          'package_sha256': manifest['package_sha256'], 'settings_save_revision': 2,
          'tests': ['two actual DE addresses under X11 animation before/after reboot',
                    'legacy KMS flips about 62.79Hz before/after reboot',
                    'real hardware WAIT_VBLANK and DPMS recovery before/after reboot',
                    'eight orientations with touch matrices; actual boot right orientation/touch',
                    '16 concurrent actual settings commands before/after reboot',
                    'one full GPU scene set with three concurrent 512MiB CPU RAM passes',
                    'normal eMMC reboot, brightness100/right/Panfrost restored'],
          'limitations': ['CPU shadow copy, no zero-copy scanout',
                          'board-specific guarded GPIO/PWM/PMIC ownership',
                          'DPMS backlight-off only; panel sleep/rail gating not qualified',
                          'subjective moving-image user confirmation recorded separately'],
          'rollback': 'python3 /home/debian/upgrade_screen_doublebuffer.py restore',
          'evidence': evidence}
with (folder/'QUALIFICATION.json').open('x', encoding='utf8') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print('TZX_SCREEN_DOUBLEBUFFER_ACTUAL_BOOT_QUALIFICATION_RECORDED', json.dumps(record))
