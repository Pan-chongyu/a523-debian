"""Pin the third loader transaction to the verified early-CPUB image."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
text = (root/'firmware/install_boot_cpub.py').read_text()
manifest = json.loads((root/'build/boot-wide-emmc/loader.toc0.json').read_text())
assert manifest['ARM_emulation_verified']


def replace(old, new):
    global text
    assert text.count(old) == 1, (old, text.count(old))
    text = text.replace(old, new)


replace('"""Install the qualified early CPUB sequence after the card identity check."""',
        '"""Install validated legacy 8-bit reads, retaining CPU clocks and load CRCs."""')
replace("OLD = '4d1b90298dfc6238ea579eab33f7ca168639f5c512c9bddfeb61c1764118c842'",
        "OLD = '70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0'")
replace("BACKUP = Path('/root/tzx-recovery/boot-early-cpub-v1')", "BACKUP = Path('/root/tzx-recovery/boot-wide-v1')")
replace("STATE = Path('/var/lib/tzx/boot-early-cpub-installed.json')", "STATE = Path('/var/lib/tzx/boot-wide-installed.json')")
replace("FOLDER = Path('/home/debian/boot-early-cpub')", "FOLDER = Path('/home/debian/boot-wide-emmc')")
replace("assert manifest['ARM_emulation_verified'] and manifest['DRAM_MMC_CRC_BL31_kernel_unchanged']\n"
        "assert manifest['CPU4_7_clock_MHz'] == 480 and manifest['voltage_and_PMIC_unchanged']",
        "assert manifest['ARM_emulation_verified'] and manifest['CRC_CPU_DRAM_BL31_kernel_unchanged']\n"
        "assert manifest['bus_width'] == 8 and manifest['clock_voltage_timing_unchanged']\n"
        "assert manifest['no_storage_data_writes'] and manifest['comparison_failure_resets_to_original_1bit']")
replace("assert len(manifest['emulation']) == 8 and all(t['result'] == 'PASS' for t in manifest['emulation'])",
        "assert len(manifest['emulation']) == 13 and all(t['result'] == 'PASS' for t in manifest['emulation'])")
replace("assert manifest['firmware_bytes'] == 33824 and manifest['hook_bytes'] == 280",
        "assert manifest['firmware_bytes'] == 34656 and manifest['hook_bytes'] == 580")
replace("assert sha(candidate[0xf80:0xf80+33824]) == manifest['firmware_sha256']",
        "assert sha(candidate[0xf80:0xf80+34656]) == manifest['firmware_sha256']")
replace("assert candidate[0xf80+33824:] == bytes(len(candidate)-0xf80-33824)",
        "assert candidate[0xf80+34656:] == bytes(len(candidate)-0xf80-34656)")
replace("assert struct.unpack_from('<I', original, patch)[0] == 0xeb0001f5",
        "assert struct.unpack_from('<I', original, patch)[0] == 0xeb001f96")
branch = 0xeb000000 | (((0x4c500-0x444a0-8)//4)&0xffffff)
replace("assert struct.unpack_from('<I', candidate, patch)[0] == 0xeb001f96",
        "assert struct.unpack_from('<I', candidate, patch)[0] == 0x%08x" % branch)
replace("assert original[patch+4:begin+33344] == candidate[patch+4:begin+33344]",
        "assert original[patch+4:begin+33824] == candidate[patch+4:begin+33824]")
replace("previous = json.loads(Path('/var/lib/tzx/boot-crc-installed.json').read_text())",
        "previous = json.loads(Path('/var/lib/tzx/boot-early-cpub-installed.json').read_text())")
replace("value['boot_early_cpub_update_boot_id'] = BOOT", "value['boot_wide_update_boot_id'] = BOOT")
replace("atomic(BACKUP/'install_boot_cpub.py', Path(__file__).read_bytes())",
        "atomic(BACKUP/'install_boot_wide.py', Path(__file__).read_bytes())")
replace("atomic(BACKUP/'fast-crc-qualified.json', proof)", "atomic(BACKUP/'early-cpub-qualified.json', proof)")
text = text.replace('early-480MHz-CPUB-installed-pending-reboot', 'validated-8bit-boot-read-installed-pending-reboot')
text = text.replace('EARLY_CPUB_', 'WIDE_BOOT_')
replace('CPU4_7_MHz=480, voltages_unchanged=True', 'CPU4_7_MHz=480, voltages_unchanged=True, boot_bus_width=8')
compile(text, 'install_boot_wide.py', 'exec')
(root/'firmware/install_boot_wide.py').write_text(text, encoding='utf-8', newline='\n')
print('WIDE_BOOT_PINNED_INSTALLER_PREPARED', hex(branch))
