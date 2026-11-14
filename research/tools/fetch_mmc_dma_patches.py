"""Archive the authored MMC fixes for review; this does not apply patches."""
import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
folder = root/'upstream/a523-mmc-dma-20261103'
folder.mkdir(exist_ok=True)
records = []
for part in (3, 4):
    name = f'{part-1:02d}.patch'
    url = f'https://patchwork.armbian.eu/project/patchwork/patch/20261103183030.81078-{part}-jernej.skrabec%40gmail.com/mbox/'
    data = urllib.request.urlopen(url, timeout=25).read(1024*1024)
    assert b'diff --git a/drivers/mmc/host/sunxi-mmc.c' in data
    assert f'20261103183030.81078-{part}-jernej.skrabec'.encode() in data
    assert b'Signed-off-by: Jernej' in data
    path = folder/name
    assert not path.exists() or path.read_bytes() == data
    path.write_bytes(data)
    records.append({'file': name, 'url': url, 'sha256': hashlib.sha256(data).hexdigest(),
                    'bytes': len(data), 'applied': False})
(folder/'SOURCES.json').write_text(json.dumps({'author': 'Jernej Skrabec',
    'date': '2026-11-03', 'scope': 'Only DMA mask and mapped SG descriptor fixes (2/4,3/4)',
    'records': records}, indent=2)+'\n')
print('MMC_DMA_AUTHORED_PATCHES_ARCHIVED', json.dumps(records))
