"""Retain the complete native-stack boot audit with the exact new TOC0 format."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
text=(root/'firmware/verify_boot_latency.py').read_text()
def replace(old,new):
    global text
    assert text.count(old)==1,(old,text.count(old))
    text=text.replace(old,new)
replace("    actual_toc0_sha256 = sha(device.read(40960))",'''    head = device.read(32)
    assert len(head)==32 and head[:8]==b'TOC0.GLH'
    length = int.from_bytes(head[28:32], 'little')
    assert length in (40960,49152)
    device.seek(256*512)
    actual_toc0_sha256 = sha(device.read(length))''')
replace("variants=('boot-hwcrc',", "variants=('boot-panel','boot-hwcrc',")
replace("wide = variant in ('boot-wide','boot-fast','boot-icache','boot-hwcrc')",
    "wide = variant in ('boot-panel','boot-wide','boot-fast','boot-icache','boot-hwcrc')")
replace("profiled = variant in ('boot-profile','boot-fast','boot-icache','boot-hwcrc')",
    "profiled = variant in ('boot-panel','boot-profile','boot-fast','boot-icache','boot-hwcrc')")
replace("installer={'boot-hwcrc':", "installer={'boot-panel':'install_boot_panel.py','boot-hwcrc':")
replace("if variant=='boot-hwcrc':", "if variant in ('boot-panel','boot-hwcrc'):")
replace("print(run('python3', '/home/debian/'+installer[variant],",
    "print(run('python3', crc.get('installer','/home/debian/'+installer[variant]),")
replace("PMIC_and_DRAM_code_unchanged=True,", "PMIC_voltage_and_DRAM_training_code_unchanged=True,")
compile(text,'verify_boot_panel_native_stack.py','exec')
(root/'firmware/verify_boot_panel_native_stack.py').write_text(text,encoding='utf-8',newline='\n')
print('EARLY_PANEL_NATIVE_STACK_AUDIT_PREPARED')
