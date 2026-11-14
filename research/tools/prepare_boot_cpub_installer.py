"""Derive the second pinned transaction from the verified CRC transaction."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
text = (root/'firmware/install_boot_crc.py').read_text()


def replace(old, new):
    global text
    assert text.count(old) == 1, (old, text.count(old))
    text = text.replace(old, new)


replace('"""Install a CRC-only TOC0 patch with pinned code, readback and exact rollback."""',
        '"""Install the qualified early CPUB sequence after the card identity check."""')
replace("OLD = '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'",
        "OLD = '4d1b90298dfc6238ea579eab33f7ca168639f5c512c9bddfeb61c1764118c842'")
replace("BACKUP = Path('/root/tzx-recovery/boot-crc-v1')", "BACKUP = Path('/root/tzx-recovery/boot-early-cpub-v1')")
replace("STATE = Path('/var/lib/tzx/boot-crc-installed.json')", "STATE = Path('/var/lib/tzx/boot-early-cpub-installed.json')")
replace("FOLDER = Path('/home/debian/boot-latency-loader')", "FOLDER = Path('/home/debian/boot-early-cpub')")
replace("assert manifest['ARM_emulation_verified'] and manifest['mmc_DRAM_PMIC_CPU_BL31_kernel_unchanged']",
        "assert manifest['ARM_emulation_verified'] and manifest['DRAM_MMC_CRC_BL31_kernel_unchanged']\n"
        "assert manifest['CPU4_7_clock_MHz'] == 480 and manifest['voltage_and_PMIC_unchanged']")
replace("assert all(t['cases'] == 128 and t['result'] == 'PASS' for t in manifest['emulation'])",
        "assert len(manifest['emulation']) == 8 and all(t['result'] == 'PASS' for t in manifest['emulation'])")
replace("assert manifest['original_toc0_sha256'] == OLD and manifest['old_instruction_changed'] == '0x44454'",
        "assert manifest['previous_toc0_sha256'] == OLD and manifest['changed_old_instruction'] == '0x444a0'")
replace("assert manifest['firmware_bytes'] == 33344 and manifest['hook_bytes'] == 1068",
        "assert manifest['firmware_bytes'] == 33824 and manifest['hook_bytes'] == 280")
replace("assert sha(candidate[0xf80:0xf80+33344]) == manifest['firmware_sha256']",
        "assert sha(candidate[0xf80:0xf80+33824]) == manifest['firmware_sha256']")
replace("assert candidate[0xf80+33344:] == bytes(len(candidate)-0xf80-33344)",
        "assert candidate[0xf80+33824:] == bytes(len(candidate)-0xf80-33824)")
replace("# All trained DRAM, PIO, failure handling and hand-off instructions\n        # remain byte-identical. Only the original CRC entry is redirected.",
        "# Preserve the trained DRAM, PIO, CRC and hand-off bytes. Redirect\n        # only the existing call to the exact-CID initialization wrapper.")
replace("patch = begin + 0x44454-0x44000", "patch = begin + 0x444a0-0x44000")
replace("assert struct.unpack_from('<I', original, patch)[0] == 0xe52de004",
        "assert struct.unpack_from('<I', original, patch)[0] == 0xeb0001f5")
branch = 0xeb000000 | (((0x4c300-0x444a0-8)//4)&0xffffff)
replace("assert struct.unpack_from('<I', candidate, patch)[0] == 0xea001e69",
        "assert struct.unpack_from('<I', candidate, patch)[0] == 0x%08x" % branch)
replace("assert original[patch+4:begin+32064] == candidate[patch+4:begin+32064]",
        "assert original[patch+4:begin+33344] == candidate[patch+4:begin+33344]")
start = text.index('        pins = {')
end = text.index('        originals = ', start)
text = text[:start]+'''        previous = json.loads(Path('/var/lib/tzx/boot-crc-installed.json').read_text())
        assert previous['toc0_sha256'] == OLD and previous['verified_boot_id'] == BOOT
        proof = Path('/var/lib/tzx/boot-latency-qualified.json').read_bytes()
        assert json.loads(proof)['boot_id'] == BOOT and json.loads(proof)['status'] == 'PASS'
        pins = {name: previous['files'][name]['installed_sha256'] for name in (
            '/usr/local/lib/tzx-dram-gpu/runtime.py',
            '/usr/local/lib/tzx-rtc-context/runtime.py',
            '/usr/local/lib/tzx-pmic-poweroff/runtime.py')}
''' + text[end:]
start = text.index("            if 'rtc-context' in name:")
end = text.index('            compile(replacements[name]', start)
text = text[:start]+'''            needle = ("'"+OLD+"')").encode()
            assert data.count(needle) == 1
            replacements[name] = data.replace(needle, ("'"+OLD+"', '"+pin+"')").encode())
''' + text[end:]
replace("value['accepted_toc0_sha256'] = [OLD, pin]", "value['accepted_toc0_sha256'].append(pin)")
replace("value['boot_crc_update_boot_id'] = BOOT", "value['boot_early_cpub_update_boot_id'] = BOOT")
replace("atomic(BACKUP/'install_boot_crc.py', Path(__file__).read_bytes())",
        "atomic(BACKUP/'install_boot_cpub.py', Path(__file__).read_bytes())\n        atomic(BACKUP/'fast-crc-qualified.json', proof)")
text = text.replace('CRC-only-installed-pending-reboot', 'early-480MHz-CPUB-installed-pending-reboot')
text = text.replace('FAST_CRC_', 'EARLY_CPUB_')
text = text.replace('runtime_accepts_exact_original_and_candidate=True',
                    'runtime_accepts_exact_previous_and_candidate=True, CPU4_7_MHz=480, voltages_unchanged=True')
compile(text, 'install_boot_cpub.py', 'exec')
(root/'firmware/install_boot_cpub.py').write_text(text, encoding='utf-8', newline='\n')
print('EARLY_CPUB_PINNED_INSTALLER_PREPARED', hex(branch))
