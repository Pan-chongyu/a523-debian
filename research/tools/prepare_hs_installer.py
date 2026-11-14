"""Specialize the verified inactive-slot installer for the HS kernel."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
text=(root/'firmware/install_extended_kernel.py').read_text()
manifest=json.loads((root/'build/hs-kernel/linux-bundle.json').read_text())
text=text.replace('extended-kernel','hs-kernel').replace('EXTENDED_KERNEL','HS_KERNEL')
text=text.replace("OLD = 'f6b644da1a8276b599c9e3f6b7944c6eb246ddd8c8adf0cbe5ba20116c6a3829'","OLD = '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'")
text=text.replace("NEW = '091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3'",f"NEW = '{manifest['sha256']}'")
text=text.replace('65536','TZX_FIRST_SLOT').replace('98304','65536').replace('TZX_FIRST_SLOT','98304')
# Undo the GPT table sanity limit replacement; this is unrelated to boot slots.
text=text.replace('count*stride <= 98304','count*stride <= 65536')
text=text.replace('14942208','15008768')
text=text.replace("len(candidate) == manifest['bytes'] == 15008768",f"len(candidate) == manifest['bytes'] == {manifest['bytes']}")
text=text.replace("Path('/root/tzx-recovery/hs-kernel')","Path('/root/tzx-recovery/hs-kernel-v4')")
text=text.replace("Path('/var/lib/tzx/hs-kernel-installed.json')","Path('/var/lib/tzx/hs-kernel-v4-installed.json')")
text=text.replace("'SWAP, ZRAM/LZ4, DMA_HEAP_SYSTEM, sun55i IOMMU for VE0/VE1 only'",repr(manifest['config_change']))
text=text.replace("'428ec704c7c2e2d1a457dd421f232ed2082850229900f67bc1902c49fb92cf59'","'59cc725631e95f3726080322e19f4868ef461035e85d6f7dd02b5be2915aced6'")
# The new slot is above the active slot; its end must remain below /boot.
text=text.replace('98304+len(candidate)//512 < 65536','98304+len(candidate)//512 < 131072')
text=text.replace("payloads(candidate, 98304)","payloads(candidate, 98304)")
text=text.replace("if i in (2, 4): assert part[3] == old_parts[i][3]","if i in (1, 2, 4): assert part[3] == old_parts[i][3]")
text=text.replace("module_abi='recompiled_allocatable_code_data_compared; MODVERSIONS_disabled'","module_abi='same_config_and_exported_header_layout; MMC_host_private_tail_extension'")
text=text.replace("print('HS_KERNEL_ACTUAL_BOOT_ROTATED_CONSOLE_PASS'","assert 'sunxi_mmc_tzx_mode' in Path('/proc/kallsyms').read_text()\n        print('HS_KERNEL_ACTUAL_BOOT_ROTATED_CONSOLE_PASS'")
(root/'firmware/install_hs_kernel.py').write_text(text)
print('HS_INACTIVE_SLOT_INSTALLER_PREPARED')
