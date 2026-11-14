"""Freeze a page-table-format comparison, retaining the preceding candidate."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
base = root / 'build/gpu-dma32-mmu-init'
source = json.loads((base / 'SOURCE.json').read_text())
out = root / 'build/gpu-dma32-aarch64'
out.mkdir(exist_ok=False)
for relative, digest in source['files'].items():
    original = base / relative
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest, relative
    destination = out / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, destination)
path = out / 'source/panfrost_mmu.c'
text = path.read_text()
needle = '\tif (pfdev->comp->gpu_quirks & BIT(GPU_QUIRK_FORCE_AARCH64_PGTABLE)) {'
assert text.count(needle) == 1
text = text.replace(needle, '''\t/* Diagnostic comparison: use the existing upstream AArch64 format.
\t * The existing DMA32 parameter already restricts this to the TZX board. */
\tif (panfrost_tzx_dma32 ||
\t    (pfdev->comp->gpu_quirks & BIT(GPU_QUIRK_FORCE_AARCH64_PGTABLE))) {''')
needle = '\tmmu->pgtbl_ops = alloc_io_pgtable_ops(fmt, &mmu->pgtbl_cfg, mmu);'
assert text.count(needle) == 1
text = text.replace(needle, '''\tif (panfrost_tzx_dma32)
\t\tdev_info_once(pfdev->base.dev, "TZX diagnostic AARCH64_4K page tables, low PA, full CPU RAM\\n");
''' + needle)
path.write_text(text, newline='\n')
source.update(purpose='DMA32_and_initial_MMU_reset_plus_upstream_AARCH64_4K_format_comparison',
              status='prepared_not_hardware_verified', persistent_gpu_enable=False,
              reference='https://lists.infradead.org/pipermail/linux-mediatek/2025-March/091402.html',
              reference_scope='Upstream G57 format support; MediaTek result is not proof for this Allwinner board')
source['files'] = {str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
                   for folder in (out / 'source', out / 'display-source') for path in folder.iterdir()}
(out / 'SOURCE.json').write_text(json.dumps(source, indent=2) + '\n', newline='\n')
print('GPU_AARCH64_COMPARISON_SOURCE_PREPARED')
