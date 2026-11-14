"""Apply authored mapped-SG fix to an isolated source tree and adapt mask cleanup."""
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root, source = map(Path, sys.argv[1:])
original = Path('/opt/a523-debian-20261109/linux-7.3.3/drivers/mmc/host/sunxi-mmc.c')
target = source/'drivers/mmc/host/sunxi-mmc.c'
before = original.read_bytes()
assert target.read_bytes() == before
folder = root/'build/mmc-dma-kernel'
folder.mkdir(exist_ok=True)
mail = root/'upstream/a523-mmc-dma-20261103/03.patch'
data = mail.read_bytes()
assert hashlib.sha256(data).hexdigest() == '7b3ffb3cd237fe24d191d5c6b8b682a8ffc962e140525173b8e5a50bce32a770'
message = BytesParser(policy=policy.default).parsebytes(data)
body = message.get_payload(decode=True)
assert body.count(b'diff --git ') == 1
patch = body[body.index(b'diff --git '):]
subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=source, input=patch, check=True)
text = target.read_text()
needle = '\tret = sunxi_mmc_resource_request(host, pdev);\n\tif (ret)\n\t\treturn ret;\n'
assert text.count(needle) == 1
replacement = needle + '''
	ret = dma_set_mask_and_coherent(&pdev->dev,
					DMA_BIT_MASK(32 + host->cfg->idma_des_shift));
	if (ret) {
		sunxi_mmc_disable(host);
		return ret;
	}
'''
text = text.replace(needle, replacement)
target.write_text(text)
assert original.read_bytes() == before
(folder/'sunxi-mmc-before.c').write_bytes(before)
(folder/'sunxi-mmc-after.c').write_bytes(target.read_bytes())
diff = subprocess.run(['diff', '-u', '--label', 'a/drivers/mmc/host/sunxi-mmc.c',
    '--label', 'b/drivers/mmc/host/sunxi-mmc.c', str(original), str(target)], capture_output=True)
assert diff.returncode == 1
(folder/'mmc-dma-backport.patch').write_bytes(diff.stdout)
record = {'scope': ['mapped DMA SG descriptors (unmodified authored patch 3/4)',
    '34-bit mask on shifted controllers (patch 2/4, cleanup adapted to older probe)'],
    'original_source_unchanged': True, 'source_tree': str(source),
    'before_sha256': hashlib.sha256(before).hexdigest(),
    'after_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
    'extra_hardware_register_writes': False, 'voltage_or_clock_changes': False,
    'mask_failure_cleanup': 'sunxi_mmc_disable then return; older kernel has no probe error_disable_mmc label'}
(folder/'SOURCE_CHANGE.json').write_text(json.dumps(record, indent=2)+'\n')
print('MMC_DMA_SOURCE_PREPARED', json.dumps(record), flush=True)
