"""Keep the DMA32 trial intact and test explicit initial MMU IRQ setup."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
original = root / 'build/gpu-dma32-trial'
out = root / 'build/gpu-dma32-mmu-init'
out.mkdir(exist_ok=True)
assert not (out/'SOURCE.json').exists(), 'Do not overwrite a completed source snapshot'
record = json.loads((original / 'SOURCE.json').read_text())
for name, digest in record['files'].items():
    path = original / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
for directory in ('source', 'display-source'):
    shutil.copytree(original / directory, out / directory, dirs_exist_ok=True)
path = out / 'source/panfrost_device.c'
text = path.read_text()
old = '''	err = panfrost_mmu_init(pfdev);
	if (err)
		goto out_gpu;

	err = panfrost_jm_init(pfdev);'''
new = '''	err = panfrost_mmu_init(pfdev);
	if (err)
		goto out_gpu;

	/* fini masks MMU IRQs. Set up AS state and IRQs for the initial
	 * probe too, before the first job can fault in its heap. */
	if (panfrost_tzx_dma32)
		panfrost_mmu_reset(pfdev);

	err = panfrost_jm_init(pfdev);'''
assert text.count(old) == 1
text = text.replace(old, new)
assert text.count('#include "panfrost_device.h"') == 1
text = text.replace('#include "panfrost_device.h"',
                    '#include "panfrost_device.h"\n#include "panfrost_drv.h"')
path.write_text(text, newline='\n')
record.update(purpose='DMA32_trial_plus_initial_MMU_reset_before_first_job',
              parent_manifest_sha256=hashlib.sha256((original/'MANIFEST.json').read_bytes()).hexdigest(),
              persistent_gpu_enable=False, status='source_prepared_not_tested')
record['files'] = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for directory in ('source', 'display-source')
                   for p in (out/directory).iterdir()}
(out/'SOURCE.json').write_text(json.dumps(record, indent=2)+'\n')
print('DMA32_MMU_INIT_TRIAL_PREPARED', len(record['files']))
