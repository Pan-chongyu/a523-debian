"""Extract the pinned GPL PHY helpers, preserving attribution and provenance."""
from pathlib import Path
import hashlib

root = Path(__file__).resolve().parents[1]
source = root / 'upstream/trimui-reference/kernel/drivers/phy-sun55i-dsi-combo.c'
data = source.read_bytes()
text = data.decode()
prefix = text[:text.index('static int sun55i_dphy_init(')]
header = ('/* Extracted for a reversible, one-shot diagnostic only.\n'
          ' * Source: MidG971/trimui_smart_pro_s @ e1b6d49cfb813aa9261935727b82b6b7d84dc9d2\n'
          f' * Source SHA256: {hashlib.sha256(data).hexdigest()}\n'
          ' */\n')
(root / 'firmware/tzx_dsi_phy.h').write_text(prefix + header, newline='\n')
print(hashlib.sha256(data).hexdigest())
