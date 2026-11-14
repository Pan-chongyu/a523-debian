"""Derive a pinned, reversible profiling transaction from the CPUB installer."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
text=(root/'firmware/install_boot_cpub.py').read_text()
manifest=json.loads((root/'build/boot-profile/loader.toc0.json').read_text())
assert manifest['ARM_emulation_verified']
def replace(old,new):
    global text
    assert text.count(old)==1,(old,text.count(old))
    text=text.replace(old,new)
replace('"""Install the qualified early CPUB sequence after the card identity check."""',
    '"""Install counters around unchanged qualified boot routines."""')
replace("OLD = '4d1b90298dfc6238ea579eab33f7ca168639f5c512c9bddfeb61c1764118c842'",
    "OLD = '70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0'")
for old,new in (('boot-early-cpub-v1','boot-profile-v1'),('boot-early-cpub-installed.json','boot-profile-installed.json'),
                ('/home/debian/boot-early-cpub','/home/debian/boot-profile')):
    text=text.replace(old,new)
replace("assert manifest['ARM_emulation_verified'] and manifest['DRAM_MMC_CRC_BL31_kernel_unchanged']\nassert manifest['CPU4_7_clock_MHz'] == 480 and manifest['voltage_and_PMIC_unchanged']",
    "assert manifest['ARM_emulation_verified'] and manifest['hardware_configuration_unchanged']\nassert manifest['SRAM_profile_address'] == '0x2dc00'")
replace("assert len(manifest['emulation']) == 8 and all(t['result'] == 'PASS' for t in manifest['emulation'])",
    "assert len(manifest['emulation']) == 5 and all(t['status'] == 'PASS' for t in manifest['emulation'])")
replace("assert manifest['previous_toc0_sha256'] == OLD and manifest['changed_old_instruction'] == '0x444a0'",
    "assert manifest['previous_toc0_sha256'] == OLD and len(manifest['patches']) == 3")
replace("assert manifest['firmware_bytes'] == 33824 and manifest['hook_bytes'] == 280",
    "assert manifest['firmware_bytes'] == 34368 and manifest['hook_bytes'] == 316")
text=text.replace('candidate[0xf80:0xf80+33824]','candidate[0xf80:0xf80+34368]').replace(
    'candidate[0xf80+33824:] == bytes(len(candidate)-0xf80-33824)',
    'candidate[0xf80+34368:] == bytes(len(candidate)-0xf80-34368)')
start=text.index('        # Preserve the trained DRAM, PIO, CRC and hand-off bytes.')
end=text.index('        for a, b in ((0, 0x0c)',start)
text=text[:start]+'''        begin = 0xf80
        expected = bytearray(original[begin:begin+33816])
        for item in manifest['patches']:
            offset = item['address']-0x44000
            assert struct.unpack_from('<I', expected, offset)[0] == item['old']
            struct.pack_into('<I', expected, offset, item['new'])
        assert candidate[begin:begin+33816] == expected
'''+text[end:]
replace("previous = json.loads(Path('/var/lib/tzx/boot-crc-installed.json').read_text())",
    "previous = json.loads(Path('/var/lib/tzx/boot-early-cpub-installed.json').read_text())")
replace("assert previous['toc0_sha256'] == OLD and previous['verified_boot_id'] == BOOT",
    "assert previous['toc0_sha256'] == OLD and previous.get('verified_boot_id')")
replace("assert json.loads(proof)['boot_id'] == BOOT and json.loads(proof)['status'] == 'PASS'",
    "assert json.loads(proof)['boot_id'] == previous['verified_boot_id'] and json.loads(proof)['status'] == 'PASS'\n"
    "        assert json.loads(proof)['toc0_sha256'] == OLD\n"
    "        for component in ('tzx-cpu-full', 'tzx-gpu-devfreq', 'tzx-emmc-hs'):\n"
    "            component_manifest = json.loads((Path('/usr/local/lib')/component/'manifest.json').read_text())\n"
    "            for name, digest in component_manifest['files'].items():\n"
    "                assert sha(Path(name).read_bytes()) == digest, name\n"
    "        for name in ('cpu-dvfs', 'gpu-performance', 'emmc-hs'):\n"
    "            live = json.loads(Path('/run/tzx-'+name+'.json').read_text())\n"
    "            assert live['boot_id'] == BOOT and live['state'] == 'active'")
text=text.replace('boot_early_cpub_update_boot_id','boot_profile_update_boot_id').replace(
    'install_boot_cpub.py','install_boot_profile.py').replace('fast-crc-qualified.json','early-cpub-qualified.json').replace(
    'early-480MHz-CPUB-installed-pending-reboot','boot-profile-installed-pending-reboot').replace(
    'EARLY_CPUB_','BOOT_PROFILE_')
compile(text,'install_boot_profile.py','exec')
(root/'firmware/install_boot_profile.py').write_text(text,encoding='utf-8',newline='\n')
print('PROFILE_BOOT_PINNED_TRANSACTION_PREPARED')
