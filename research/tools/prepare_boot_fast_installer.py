"""Pin the reversible measured reader/word-CRC update."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
text=(root/'firmware/install_boot_profile.py').read_text()
m=json.loads((root/'build/boot-fast/loader.toc0.json').read_text());assert m['ARM_emulation_verified']
def replace(old,new):
    global text
    assert text.count(old)==1,(old,text.count(old))
    text=text.replace(old,new)
replace('"""Install counters around unchanged qualified boot routines."""',
    '"""Install the measured 8-bit pin-mux reader and aligned word CRC."""')
replace("OLD = '70efff1506d33cd90931197b5b558cace64720dca5e4b7a3d6db688851526db0'",
    "OLD = '4ae89856592e7b95fde5d0b40e49a09255f9745470fa9cc22bc64a06319ac4bc'")
for old,new in (('boot-profile-v1','boot-fast-v1'),('boot-profile-installed.json','boot-fast-installed.json'),
                ('/home/debian/boot-profile','/home/debian/boot-fast')):text=text.replace(old,new)
replace("assert manifest['ARM_emulation_verified'] and manifest['hardware_configuration_unchanged']",
    "assert manifest['ARM_emulation_verified'] and manifest['clock_voltage_timing_unchanged']\n"
    "assert manifest['pins_match_qualified_Linux_DT'] and manifest['no_storage_data_writes']\n"
    "assert manifest['CRC_polynomial_seed_unchanged'] and len(manifest['CRC_emulation']) == 64\n"
    "assert all(t['status'] == 'PASS' for t in manifest['CRC_emulation'])")
replace("assert len(manifest['emulation']) == 5 and all(t['status'] == 'PASS' for t in manifest['emulation'])",
    "assert len(manifest['emulation']) == 13 and all(t['result'] == 'PASS' for t in manifest['emulation'])")
replace("assert manifest['previous_toc0_sha256'] == OLD and len(manifest['patches']) == 3",
    "assert manifest['previous_toc0_sha256'] == OLD and len(manifest['patches']) == 2")
replace("assert manifest['firmware_bytes'] == 34368 and manifest['hook_bytes'] == 316",
    "assert manifest['firmware_bytes'] == 35744 and manifest['hook_bytes'] == 836")
text=text.replace('0xf80+34368','0xf80+35744').replace('0xf80-34368','0xf80-35744').replace('len(candidate)-0xf80-34368','len(candidate)-0xf80-35744')
text=text.replace('begin+33816','begin+34364')
replace("previous = json.loads(Path('/var/lib/tzx/boot-early-cpub-installed.json').read_text())",
    "previous = json.loads(Path('/var/lib/tzx/boot-profile-installed.json').read_text())")
text=text.replace('boot_profile_update_boot_id','boot_fast_update_boot_id').replace('install_boot_profile.py','install_boot_fast.py').replace(
    'early-cpub-qualified.json','profile-qualified.json').replace('boot-profile-installed-pending-reboot','boot-fast-installed-pending-reboot').replace('BOOT_PROFILE_','BOOT_FAST_')
compile(text,'install_boot_fast.py','exec')
(root/'firmware/install_boot_fast.py').write_text(text,encoding='utf-8',newline='\n')
print('FAST_BOOT_PINNED_TRANSACTION_PREPARED')
