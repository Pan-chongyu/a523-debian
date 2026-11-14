"""Add the board's helper selections without changing the verified #9 output."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
source = Path('/opt/a523-debian-20261109/linux-7.3.3')
kconfig = source / 'drivers/gpu/drm/Kconfig'
text = kconfig.read_text()
entry = '\nsource "drivers/gpu/drm/tzx/Kconfig"\n'
if entry not in text:
    kconfig.write_text(text + entry)
board = source / 'drivers/gpu/drm/tzx'
board.mkdir(exist_ok=True)
(board / 'Kconfig').write_bytes((root / 'firmware/tzx_display.Kconfig').read_bytes())
