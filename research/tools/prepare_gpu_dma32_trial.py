"""Copy Panfrost sources and add an opt-in, board-only low-PA diagnostic mode."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = Path(r'\\wsl.localhost\Ubuntu-22.04\opt\a523-debian-20261109\linux-7.3.3\drivers\gpu\drm\panfrost')
out = root / 'build/gpu-dma32-trial/source'
out.mkdir(parents=True, exist_ok=False)
for path in source.iterdir():
    if path.suffix in ('.c', '.h') or path.name == 'Makefile':
        (out/path.name).write_bytes(path.read_bytes())

def replace(name, old, new):
    path = out/name
    text = path.read_text()
    assert text.count(old) == 1, (name, old, text.count(old))
    path.write_text(text.replace(old,new),newline='\n')

replace('panfrost_drv.c', 'static bool unstable_ioctls;', '''/* Diagnostic parameter, deliberately off by default and never auto-loaded. */
bool panfrost_tzx_dma32;
module_param_named(tzx_dma32, panfrost_tzx_dma32, bool, 0444);
MODULE_PARM_DESC(tzx_dma32, "TZX P30 diagnostic: keep GPU data and page tables below 4GB");

static bool unstable_ioctls;''')
replace('panfrost_drv.h', 'extern bool panfrost_transparent_hugepage;',
        'extern bool panfrost_transparent_hugepage;\nextern bool panfrost_tzx_dma32;')
replace('panfrost_drv.c', '\tpfdev->coherent = device_get_dma_attr(&pdev->dev) == DEV_DMA_COHERENT;', '''
	if (panfrost_tzx_dma32 && !of_machine_is_compatible("tzx,p30a523"))
		return -ENODEV;
	pfdev->coherent = device_get_dma_attr(&pdev->dev) == DEV_DMA_COHERENT;''')
replace('panfrost_gem.c', '#include <linux/dma-mapping.h>',
        '#include <linux/dma-mapping.h>\n#include <linux/pagemap.h>')
replace('panfrost_gem.c', '\tbo = to_panfrost_bo(&shmem->base);\n\tbo->noexec = !!(flags & PANFROST_BO_NOEXEC);', '''
	/* The shmem helper has initialized filp, but no pages exist yet. This
	 * includes heap pages subsequently allocated by the MMU fault handler. */
	if (panfrost_tzx_dma32)
		mapping_set_gfp_mask(shmem->base.filp->f_mapping,
			GFP_USER | __GFP_DMA32 | __GFP_RETRY_MAYFAIL | __GFP_NOWARN);
	bo = to_panfrost_bo(&shmem->base);
	bo->noexec = !!(flags & PANFROST_BO_NOEXEC);''')
replace('panfrost_mmu.c', '#include "panfrost_device.h"',
        '#include "panfrost_device.h"\n#include "panfrost_drv.h"')
replace('panfrost_mmu.c', 'struct panfrost_mmu *panfrost_mmu_ctx_create(struct panfrost_device *pfdev)', '''static void *tzx_dma32_pt_alloc(void *cookie, size_t size, gfp_t gfp)
{
	void *memory = alloc_pages_exact(size, (gfp & ~GFP_ZONEMASK) |
					__GFP_DMA32 | __GFP_ZERO);
	if (memory && (virt_to_phys(memory) + size - 1) >> 32) {
		free_pages_exact(memory, size);
		return NULL;
	}
	return memory;
}
static void tzx_dma32_pt_free(void *cookie, void *memory, size_t size)
{
	free_pages_exact(memory, size);
}

struct panfrost_mmu *panfrost_mmu_ctx_create(struct panfrost_device *pfdev)''')
replace('panfrost_mmu.c', '\tmmu->pgtbl_ops = alloc_io_pgtable_ops(fmt, &mmu->pgtbl_cfg, mmu);', '''
	if (panfrost_tzx_dma32) {
		mmu->pgtbl_cfg.oas = 32;
		mmu->pgtbl_cfg.alloc = tzx_dma32_pt_alloc;
		mmu->pgtbl_cfg.free = tzx_dma32_pt_free;
	}
	mmu->pgtbl_ops = alloc_io_pgtable_ops(fmt, &mmu->pgtbl_cfg, mmu);''')
replace('panfrost_mmu.c', '\t\tsize_t len = sg_dma_len(sgl);\n\n\t\tdev_dbg', '''
		size_t len = sg_dma_len(sgl);
		if (panfrost_tzx_dma32 && ((u64)paddr + len - 1) >> 32) {
			dev_err(pfdev->base.dev, "TZX DMA32: rejected high DMA address %lx+%zx\\n", paddr, len);
			ret = -ERANGE;
			goto err_unmap_pages;
		}

		dev_dbg''')
# Mapping failure must not release the page reference owned by cached shmem->sgt.
# This matters when the diagnostic guard deliberately rejects a high import.
replace('panfrost_mmu.c', '''	if (ret)
		goto err_put_pages;

	mapping->active = true;

	return 0;

err_put_pages:
	drm_gem_shmem_put_pages_locked(shmem);
	return ret;''', '''	if (ret)
		return ret;

	mapping->active = true;

	return 0;''')
replace('panfrost_mmu.c', '''			if (ret)
				goto err_unmap_pages;

			/* Don't get stuck''', '''			if (ret) {
				total_mapped += mapped;
				goto err_unmap_pages;
			}

			/* Don't get stuck''')
replace('panfrost_mmu.c', '''err_unmap_pages:
	mmu_unmap_range(mmu, start_iova, total_mapped);
	return ret;''', '''err_unmap_pages:
	if (total_mapped) {
		mmu_unmap_range(mmu, start_iova, total_mapped);
		panfrost_mmu_flush_range(pfdev, mmu, start_iova, total_mapped);
	}
	return ret;''')

display = root/'build/gpu-dma32-trial/display-source'
display.mkdir(exist_ok=False)
for name in ('tzx_drm.c','tzx_de_scanout.c','tzx_dsi_probe.c','tzx_dsi_phy.h','tzx_dsi_video.h'):
    (display/name).write_bytes((root/'firmware'/name).read_bytes())
path=display/'tzx_drm.c'; text=path.read_text()
text=text.replace('#include <linux/highmem.h>', '#include <linux/highmem.h>\n#include <linux/pagemap.h>')
marker='static const struct drm_display_mode panel_mode = {'
assert text.count(marker)==1
text=text.replace(marker,'''/* Limit only KMS dumb buffers that can be exported to the GPU. CPU RAM
 * remains fully available; this source is a separate diagnostic build. */
static int tzx_dma32_dumb_create(struct drm_file *file, struct drm_device *drm,
                               struct drm_mode_create_dumb *args)
{
    struct drm_gem_object *obj;
    int ret = drm_gem_shmem_dumb_create(file, drm, args);
    if (ret) return ret;
    obj = drm_gem_object_lookup(file, args->handle);
    if (!obj) return -ENOENT;
    mapping_set_gfp_mask(obj->filp->f_mapping,
                        GFP_USER | __GFP_DMA32 | __GFP_RETRY_MAYFAIL | __GFP_NOWARN);
    drm_gem_object_put(obj);
    return 0;
}
''' + marker)
assert text.count('.dumb_create = drm_gem_shmem_dumb_create,')==1
text=text.replace('.dumb_create = drm_gem_shmem_dumb_create,','.dumb_create = tzx_dma32_dumb_create,')
text=text.replace('.major = 1, .minor = 2,','.major = 1, .minor = 3,')
path.write_text(text,newline='\n')
manifest={'purpose':'diagnostic_only_opt_in_GPU_PA_below_4GB_with_full_4GiB_CPU_RAM',
          'persistent_gpu_enable':False,'kernel':'7.3.3-tzx-a523-accel1 #4',
          'source_kernel_dir':str(source),'files':{}}
for base in (out,display):
    for f in base.iterdir():
        manifest['files'][str(f.relative_to(root/'build/gpu-dma32-trial'))]=hashlib.sha256(f.read_bytes()).hexdigest()
(out.parent/'SOURCE.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('GPU_DMA32_DIAGNOSTIC_SOURCES_PREPARED',len(manifest['files']))
