"""Freeze independent evidence for panel standby after the actual eMMC reboot."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root/'build/screen-standby'
manifest = json.loads((folder/'screen-runtime-standby-FILES.json').read_text())
source = json.loads((folder/'SOURCE.json').read_text())
for name, digest in source['files'].items():
    assert hashlib.sha256((folder/'source'/name).read_bytes()).hexdigest() == digest
module = manifest['files']['usr/local/lib/tzx-screen/tzx_display.ko']['sha256']
assert hashlib.sha256((folder/'tzx_display.ko').read_bytes()).hexdigest() == module
observer = json.loads((root/'evidence/screen-standby-actual-reboot-observer.json').read_text())
assert observer['state'] == 'SSH_READY'
assert observer['linux_boot_id'] != '69318e67-aa6a-4bb5-82cc-d5ad85c5e78d'
required = {
    'screen-standby-five-cycle-manual.txt': ['TZX_SCREEN_DCS_SLEEP_VIDEO_STOP_AND_WAKE_PASS'],
    'screen-standby-manual-controls-flips.txt': ['TZX_SCREEN_FOUR_ORIENTATIONS_AND_TOUCH_MATRIX_PASS',
                                             'TZX_SCREEN_KMS_PAGEFLIP_EVENTS_PASS'],
    'screen-standby-actual-boot-validation.txt': ['TZX_SCREEN_ACTUAL_REBOOT_BRIGHTNESS_ROTATION_TOUCH_GPU_PASS',
                                              'TZX_SCREEN_DCS_SLEEP_VIDEO_STOP_AND_WAKE_PASS',
                                              'TZX_SCREEN_HARDWARE_DRM_VBLANK_DPMS_PASS',
                                              'TZX_SCREEN_DUAL_DMA_RCQ_ADDRESS_ANIMATION_PASS',
                                              'TZX_SCREEN_KMS_PAGEFLIP_EVENTS_PASS'],
    'screen-standby-final-file-audit.txt': ['MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS',
                                         'ActiveState=inactive', 'ExecMainStatus=0', 'Result=success'],
}
evidence = {}
for name, markers in required.items():
    data = (root/'evidence'/name).read_bytes()
    text = data.decode('utf8')
    assert 'Traceback' not in text and all(marker in text for marker in markers), name
    if name == 'screen-standby-actual-boot-validation.txt':
        assert observer['linux_boot_id'] in text
    evidence['evidence/'+name] = hashlib.sha256(data).hexdigest()
record = {'revision': 'screen-functions-4-standby', 'qualification': 'bounded hardware tests and actual eMMC boot',
          'manual_boot_id': '69318e67-aa6a-4bb5-82cc-d5ad85c5e78d',
          'actual_autostart_boot_id': observer['linux_boot_id'], 'module_sha256': module,
          'package_sha256': manifest['package_sha256'],
          'features': ['standard DCS sleep/display-off and wake/normal-data',
                       'DSI HSD stopped while asleep; video jump chain and HSC restored before output',
                       'real hardware vblank, double-buffer RCQ addresses, about 62.79Hz pageflip',
                       'brightness, orientation, touch alignment and accelerated desktop persistence'],
          'panel_get_power_mode': {'sleep': '0x08', 'awake': '0x18'},
          'limitations': ['known bias and supply remain on; no full rail gating',
                          'no system suspend/hibernate support',
                          'board-specific guarded GPIO/PWM/PMIC ownership',
                          'CPU shadow copy; no zero-copy scanout',
                          'subjective user confirmation recorded separately'],
          'rollback': 'python3 /home/debian/upgrade_screen_standby.py restore', 'evidence': evidence}
with (folder/'QUALIFICATION.json').open('x', encoding='utf8') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print('TZX_SCREEN_STANDBY_QUALIFICATION_RECORDED', json.dumps(record))
