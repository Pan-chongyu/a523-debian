"""Pin the instruction-cache transaction to the actual measured 38s boot."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
text=(root/'firmware/install_boot_fast.py').read_text()
def replace(old,new):
    global text
    assert text.count(old)==1,(old,text.count(old))
    text=text.replace(old,new)
replace('"""Install the measured 8-bit pin-mux reader and aligned word CRC."""',
    '"""Enable temporary boot instruction cache, restoring it on every exit."""')
replace("OLD = '4ae89856592e7b95fde5d0b40e49a09255f9745470fa9cc22bc64a06319ac4bc'",
    "OLD = '319cdcc46804ce7136b5f00479dd6c320bc561340ea285655293de3665ab179e'")
for old,new in (('boot-fast-v1','boot-icache-v1'),('boot-fast-installed.json','boot-icache-installed.json'),
                ('/home/debian/boot-fast','/home/debian/boot-icache')):text=text.replace(old,new)
start=text.index("assert manifest['ARM_emulation_verified']")
end=text.index("assert struct.unpack_from('<I', candidate, 0x64)",start)
text=text[:start]+'''assert manifest['ARM_emulation_verified'] and manifest['instruction_cache_only']
assert manifest['MMU_data_cache_voltage_clocks_unchanged']
assert manifest['original_control_restored_before_handoff']
assert manifest['SRAM_receipt_address'] == '0x2dfc0'
assert len(manifest['emulation']) == 7 and all(t['status'] == 'PASS' for t in manifest['emulation'])
assert manifest['previous_toc0_sha256'] == OLD and len(manifest['patches']) == 3
assert manifest['firmware_bytes'] == 36672 and manifest['hook_bytes'] == 316
assert sha(candidate[0xf80:0xf80+36672]) == manifest['firmware_sha256']
assert candidate[0xf80+36672:] == bytes(len(candidate)-0xf80-36672)
'''+text[end:]
text=text.replace('begin+34364','begin+35736')
replace("previous = json.loads(Path('/var/lib/tzx/boot-profile-installed.json').read_text())",
    "previous = json.loads(Path('/var/lib/tzx/boot-fast-installed.json').read_text())")
text=text.replace('boot_fast_update_boot_id','boot_icache_update_boot_id').replace('install_boot_fast.py','install_boot_icache.py').replace(
    'profile-qualified.json','fast-pins-qualified.json').replace('boot-fast-installed-pending-reboot','boot-icache-installed-pending-reboot').replace('BOOT_FAST_','BOOT_ICACHE_')
compile(text,'install_boot_icache.py','exec')
(root/'firmware/install_boot_icache.py').write_text(text,encoding='utf-8',newline='\n')
print('ICACHE_BOOT_PINNED_TRANSACTION_PREPARED')
