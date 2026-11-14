"""Specialize the reviewed two-slot installer for the additive kernel."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
m=json.loads((root/'build/extended-kernel/linux-bundle.json').read_text())
s=(root/'firmware/install_screen_boot_kernel.py').read_text()
replacements={
    '98304':'@NEW_SLOT@','65536':'@OLD_SLOT@',
    '14942208':'@NEW_LENGTH@','14876672':'@OLD_LENGTH@',
    '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c':'@OLD_HASH@',
    'f6b644da1a8276b599c9e3f6b7944c6eb246ddd8c8adf0cbe5ba20116c6a3829':'@NEW_HASH@',
    '428ec704c7c2e2d1a457dd421f232ed2082850229900f67bc1902c49fb92cf59':'@NEW_CONFIG@',
    'ba01595843f6ca6b37f058a89fd9ec0db4cc0bb38031a1523be44cc6f54095f3':'@OLD_CONFIG@',
}
for before,after in replacements.items(): s=s.replace(before,after)
for before,after in {
    '@NEW_SLOT@':'65536','@OLD_SLOT@':'98304',
    '@NEW_LENGTH@':str(m['bytes']),'@OLD_LENGTH@':'14942208',
    '@OLD_HASH@':m['previous_bundle_sha256'],'@NEW_HASH@':m['sha256'],
    '@NEW_CONFIG@':m['config_sha256'],'@OLD_CONFIG@':'428ec704c7c2e2d1a457dd421f232ed2082850229900f67bc1902c49fb92cf59',
}.items(): s=s.replace(before,after)
s=s.replace('screen-boot-kernel','extended-kernel').replace('SCREEN_BOOT_KERNEL','EXTENDED_KERNEL')
s=s.replace('CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y',m['config_change'])
s=s.replace('if i in (1, 2, 4)', 'if i in (2, 4)')
s=s.replace('65536+len(candidate)//512 < 131072','65536+len(candidate)//512 < 98304')
s=s.replace("module_abi='existing_symbol_CRCs_unchanged'", "module_abi='recompiled_allocatable_code_data_compared; MODVERSIONS_disabled'")
s=s.replace('assert 0 < count*stride <= 98304','assert 0 < count*stride <= 65536')
s=s.replace('Stage and select the fbcon-rotation kernel','Stage and select the additive swap/video kernel')
(root/'firmware/install_extended_kernel.py').write_text(s)
print('GENERATED_EXTENDED_KERNEL_INSTALLER')
