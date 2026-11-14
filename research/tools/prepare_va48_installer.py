"""Derive the pinned spare-slot installer from the reviewed #6 transaction."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'firmware/install_pagecheck_kernel.py').read_text()
source=source.replace('pagecheck','va48').replace('PAGECHECK','VA48')
replacements={
 "os.uname().release == '7.3.3-tzx-a523-accel1'":"os.uname().release in ('7.3.3-tzx-a523-accel1', '7.3.3-tzx-a523-va48')",
 "('#5 ', '#6 ' )":"('#5 ', '#7 ')",
 "('#5 ', '#6 '))":"('#5 ', '#7 '))",
 "606a18d4eeeee98ccdff67fca33911437380e79b970a504f2356ba99dec37116":"f4055eda1458b18800f99661ed625e081af477eb521b4ac7db0b79cada356b16",
 "8eb3abbbfc1ad05214d65cd63ac7ec145398782c3e858d20095d5f24ae660972":"92cce18e904af67d1d04162d9fe98070a552ad4c728577464314c7b415468755",
 "98304, 15020032":"98304, 14811136",
 "d741bbc184836bfc08cbbf6667f056d6a5b826f0c84c12b301b0cbfede9215c9":"e4513e05449da185c5835b3e303bb4fa852a366811f892241d5268a620e33662",
 'diagnostic_6_reboot_pending':'diagnostic_7_reboot_pending',
 'diagnostic_6_slot_lba':'diagnostic_7_slot_lba',
}
for before,after in replacements.items():
    if before in source:source=source.replace(before,after)
source=source.replace('#6 diagnostic', '#7 diagnostic')
needle='new_expected = {name: sha(data) for name, data in new_mirrors.items()}'
source=source.replace(needle,"# Preserve the original release's config in its own namespace.\n"
    "original_config = Path('/boot/config-7.3.3-tzx-a523-accel1')\n"
    "assert sha(original_config.read_bytes()) == old_expected[str(original_config)]\n"
    "new_mirrors[str(original_config)] = original_config.read_bytes()\n"+needle)
assert "('#5 ', '#7 '))" in source
assert '15020032' not in source and '606a18' not in source and '#6 ' not in source
compile(source,'install_va48_kernel.py','exec')
target=root/'firmware/install_va48_kernel.py'
assert not target.exists()
target.write_text(source,encoding='utf8',newline='\n')
print('VA48_INSTALLER_PREPARED',hashlib.sha256(target.read_bytes()).hexdigest())
