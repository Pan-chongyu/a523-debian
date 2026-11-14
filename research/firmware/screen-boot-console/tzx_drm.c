// SPDX-License-Identifier: GPL-2.0-or-later
/* Fixed 800x1280 A523 panel: DRM shmem buffers copied to a permanent DMA
 * scanout buffer. This avoids retiring a GEM buffer still fetched by DE.
 * The established DSI/PHY/panel path lives in the same module.
 */
#define TZX_DRM_BUILD
#include "tzx_de_scanout.c"
#include <linux/dma-buf.h>
#include <linux/dma-resv.h>
#include <linux/highmem.h>
#include <linux/pagemap.h>
#include <linux/iosys-map.h>
#include <drm/clients/drm_client_setup.h>
#include <drm/drm_atomic_helper.h>
#include <drm/drm_connector.h>
#include <drm/drm_drv.h>
#include <drm/drm_fbdev_shmem.h>
#include <drm/drm_fourcc.h>
#include <drm/drm_framebuffer.h>
#include <drm/drm_gem_atomic_helper.h>
#include <drm/drm_gem_framebuffer_helper.h>
#include <drm/drm_gem_shmem_helper.h>
#include <drm/drm_managed.h>
#include <drm/drm_modeset_helper.h>
#include <drm/drm_probe_helper.h>
#include <drm/drm_prime.h>
#include <drm/drm_print.h>
#include <drm/drm_simple_kms_helper.h>

extern int tzx_panel_init(void);
extern void tzx_panel_exit(void);
extern void tzx_panel_blank(bool blank);
extern int tzx_panel_frame_ready(void);
extern int tzx_panel_set_sleep(bool sleep, int *status);

struct tzx_drm {
    struct drm_device drm;
    struct drm_simple_display_pipe pipe;
    struct drm_connector connector;
    struct mutex update_lock;
};
static struct tzx_drm *display;
static bool panel_started, hardware_started, drm_registered;
static char screen_revision[] = "screen-functions-5-poweron";
module_param_string(screen_revision, screen_revision, sizeof(screen_revision), 0444);
#include "tzx_screen_vblank.inc"
#include "tzx_screen_doublebuffer.inc"
#include "tzx_screen_standby.inc"

/* Generic PRIME mapping uses SKIP_CPU_SYNC and assumes the exporter handles
 * cache ownership. Native shmem objects here are CPU-cached and can also be
 * imported into the non-coherent GPU; provide that ownership transition. */
static struct sg_table *tzx_prime_map(struct dma_buf_attachment *attach,
                                     enum dma_data_direction dir)
{
    struct sg_table *sgt = drm_gem_map_dma_buf(attach, dir);
    if (!IS_ERR(sgt)) {
        dma_sync_sgtable_for_device(attach->dev, sgt, dir);
        attach->priv = sgt;
    }
    return sgt;
}
static void tzx_prime_unmap(struct dma_buf_attachment *attach,
                            struct sg_table *sgt, enum dma_data_direction dir)
{
    dma_sync_sgtable_for_cpu(attach->dev, sgt, dir);
    attach->priv = NULL;
    drm_gem_unmap_dma_buf(attach, sgt, dir);
}
static int tzx_prime_begin_cpu(struct dma_buf *dmabuf, enum dma_data_direction dir)
{
    struct drm_gem_object *obj = dmabuf->priv;
    struct drm_gem_shmem_object *shmem = to_drm_gem_shmem_obj(obj);
    struct dma_buf_attachment *attach;

    dma_resv_lock(obj->resv, NULL);
    list_for_each_entry(attach, &dmabuf->attachments, node) {
        struct sg_table *sgt = attach->priv;
        if (sgt) dma_sync_sgtable_for_cpu(attach->dev, sgt, dir);
    }
    if (shmem->vaddr) invalidate_kernel_vmap_range(shmem->vaddr, obj->size);
    dma_resv_unlock(obj->resv);
    return 0;
}
static int tzx_prime_end_cpu(struct dma_buf *dmabuf, enum dma_data_direction dir)
{
    struct drm_gem_object *obj = dmabuf->priv;
    struct drm_gem_shmem_object *shmem = to_drm_gem_shmem_obj(obj);
    struct dma_buf_attachment *attach;

    dma_resv_lock(obj->resv, NULL);
    if (shmem->vaddr) flush_kernel_vmap_range(shmem->vaddr, obj->size);
    list_for_each_entry(attach, &dmabuf->attachments, node) {
        struct sg_table *sgt = attach->priv;
        if (sgt) dma_sync_sgtable_for_device(attach->dev, sgt, dir);
    }
    dma_resv_unlock(obj->resv);
    return 0;
}
static const struct dma_buf_ops tzx_prime_ops = {
    .attach = drm_gem_map_attach, .detach = drm_gem_map_detach,
    .map_dma_buf = tzx_prime_map, .unmap_dma_buf = tzx_prime_unmap,
    .release = drm_gem_dmabuf_release, .mmap = drm_gem_dmabuf_mmap,
    .vmap = drm_gem_dmabuf_vmap, .vunmap = drm_gem_dmabuf_vunmap,
    .begin_cpu_access = tzx_prime_begin_cpu, .end_cpu_access = tzx_prime_end_cpu,
};
static struct dma_buf *tzx_prime_export(struct drm_gem_object *obj, int flags)
{
    struct dma_buf_export_info info = {
        .exp_name = KBUILD_MODNAME, .owner = THIS_MODULE, .ops = &tzx_prime_ops,
        .size = obj->size, .flags = flags, .priv = obj, .resv = obj->resv,
    };
    return drm_gem_dmabuf_export(obj->dev, &info);
}
static struct drm_gem_object *tzx_prime_import(struct drm_device *drm, struct dma_buf *dmabuf)
{
    if (dmabuf->ops == &tzx_prime_ops) {
        struct drm_gem_object *obj = dmabuf->priv;
        if (obj->dev == drm) { drm_gem_object_get(obj); return obj; }
    }
    return drm_gem_shmem_prime_import_no_map(drm, dmabuf);
}
static const struct drm_gem_object_funcs tzx_gem_funcs = {
    .free = drm_gem_shmem_object_free, .print_info = drm_gem_shmem_object_print_info,
    .pin = drm_gem_shmem_object_pin, .unpin = drm_gem_shmem_object_unpin,
    .get_sg_table = drm_gem_shmem_object_get_sg_table, .export = tzx_prime_export,
    .vmap = drm_gem_shmem_object_vmap, .vunmap = drm_gem_shmem_object_vunmap,
    .mmap = drm_gem_shmem_object_mmap, .vm_ops = &drm_gem_shmem_vm_ops,
};
static struct drm_gem_object *tzx_gem_create(struct drm_device *drm, size_t size)
{
    struct drm_gem_shmem_object *shmem = kzalloc(sizeof(*shmem), GFP_KERNEL);
    if (!shmem) return ERR_PTR(-ENOMEM);
    shmem->base.funcs = &tzx_gem_funcs;
    return &shmem->base;
}
/* Limit only KMS dumb buffers that can be exported to the GPU. CPU RAM
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
static const struct drm_display_mode panel_mode = {
    .clock = 72000,
    .hdisplay = WIDTH, .hsync_start = 840, .hsync_end = 860, .htotal = 880,
    .vdisplay = HEIGHT, .vsync_start = 1292, .vsync_end = 1296, .vtotal = 1303,
    .width_mm = 135, .height_mm = 216,
    .flags = DRM_MODE_FLAG_NHSYNC | DRM_MODE_FLAG_NVSYNC,
    .type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int connector_modes(struct drm_connector *connector)
{
    struct drm_display_mode *mode = drm_mode_duplicate(connector->dev, &panel_mode);
    if (!mode) return -ENOMEM;
    drm_mode_set_name(mode); drm_mode_probed_add(connector, mode);
    connector->display_info.width_mm = panel_mode.width_mm;
    connector->display_info.height_mm = panel_mode.height_mm;
    connector->display_info.bpc = 8;
    return 1;
}
static const struct drm_connector_helper_funcs connector_helpers = { .get_modes = connector_modes };
static const struct drm_connector_funcs connector_funcs = {
    .fill_modes = drm_helper_probe_single_connector_modes,
    .destroy = drm_connector_cleanup,
    .reset = drm_atomic_helper_connector_reset,
    .atomic_duplicate_state = drm_atomic_helper_connector_duplicate_state,
    .atomic_destroy_state = drm_atomic_helper_connector_destroy_state,
};
static enum drm_mode_status mode_valid(struct drm_simple_display_pipe *pipe,
                                      const struct drm_display_mode *mode)
{
    return drm_mode_equal(mode, &panel_mode) ? MODE_OK : MODE_BAD;
}
static int copy_frame(struct drm_plane_state *state)
{
    struct drm_framebuffer *frame = state->fb;
    struct drm_shadow_plane_state *shadow = to_drm_shadow_plane_state(state);
    struct drm_gem_object *obj;
    struct dma_buf *dmabuf = NULL;
    unsigned int x = state->src_x >> 16, y = state->src_y >> 16;
    int ret;
    void *destination;
    if (!frame || screen_panel_sleeping) return -EPIPE;
    /* begin_fb_access establishes the mapping before commit-tail. Mapping
     * here would violate dma-buf reservation locking in atomic_update. */
    if (drm_WARN_ON_ONCE(&display->drm, iosys_map_is_null(&shadow->data[0]))) return -EINVAL;
    obj = drm_gem_fb_get_obj(frame, 0);
    /* The generic framebuffer helper syncs imports only. KMSRO instead
     * exports our native dumb BO to Panfrost, so sync that case as well. */
    if (!drm_gem_is_imported(obj)) {
        mutex_lock(&obj->dev->object_name_lock);
        dmabuf = obj->dma_buf;
        if (dmabuf) get_dma_buf(dmabuf);
        mutex_unlock(&obj->dev->object_name_lock);
    }
    if (dmabuf) {
        ret = dma_buf_begin_cpu_access(dmabuf, DMA_FROM_DEVICE);
        if (ret) { dma_buf_put(dmabuf); return ret; }
    }
    ret = drm_gem_fb_begin_cpu_access(frame, DMA_FROM_DEVICE);
    if (ret) { drm_err_ratelimited(&display->drm, "CPU access failed %d\n", ret); goto end; }
    mutex_lock(&display->update_lock);
    destination = screen_back_buffer();
    if (!destination) { ret = -EIO; goto unlock; }
    for (unsigned int row = 0; row < HEIGHT; row++)
        iosys_map_memcpy_from(destination + row * WIDTH * 4, &shadow->data[0],
                             (row + y) * frame->pitches[0] + x * 4, WIDTH * 4);
    dma_wmb();
    ret = screen_commit_back_buffer();
unlock:
    mutex_unlock(&display->update_lock);
    drm_gem_fb_end_cpu_access(frame, DMA_FROM_DEVICE);
end:
    if (dmabuf) {
        dma_buf_end_cpu_access(dmabuf, DMA_FROM_DEVICE);
        dma_buf_put(dmabuf);
    }
    return ret;
}
static void pipe_enable(struct drm_simple_display_pipe *pipe,
                        struct drm_crtc_state *crtc, struct drm_plane_state *plane)
{
    if (screen_panel_resume()) return;
    if (copy_frame(plane)) {
        tzx_panel_blank(true);
        drm_err(&display->drm, "first frame failed; backlight remains off\n");
        return;
    }
    /* RCQ FINISH and active-address readback have completed. Never expose
     * TCON's temporary pattern or an uncommitted framebuffer on the glass. */
    if (tzx_panel_frame_ready()) {
        tzx_panel_blank(true);
        drm_err(&display->drm, "pixel source not ready; fixed black retained\n");
        return;
    }
    drm_crtc_vblank_on(&pipe->crtc);
    tzx_panel_blank(false);
}
static void pipe_update(struct drm_simple_display_pipe *pipe, struct drm_plane_state *old)
{
    int held = drm_crtc_vblank_get(&pipe->crtc);
    copy_frame(pipe->plane.state);
    screen_send_event(pipe);
    if (!held) drm_crtc_vblank_put(&pipe->crtc);
}
static void pipe_disable(struct drm_simple_display_pipe *pipe)
{
    drm_crtc_vblank_off(&pipe->crtc);
    screen_panel_suspend();
}
static const struct drm_simple_display_pipe_funcs pipe_funcs = {
    .mode_valid = mode_valid, .enable = pipe_enable, .disable = pipe_disable,
    .update = pipe_update,
    .enable_vblank = screen_enable_vblank,
    .disable_vblank = screen_disable_vblank,
    DRM_GEM_SIMPLE_DISPLAY_PIPE_SHADOW_PLANE_FUNCS,
};
static const struct drm_mode_config_funcs config_funcs = {
    .fb_create = drm_gem_fb_create_with_dirty,
    .atomic_check = drm_atomic_helper_check,
    .atomic_commit = drm_atomic_helper_commit,
};
DEFINE_DRM_GEM_FOPS(tzx_drm_fops);
static const struct drm_driver tzx_drm_driver = {
    .driver_features = DRIVER_GEM | DRIVER_MODESET | DRIVER_ATOMIC,
    .name = "tzx-a523", .desc = "TZX A523 800x1280 DSI display",
    .major = 1, .minor = 8,
    .fops = &tzx_drm_fops,
    .dumb_create = tzx_dma32_dumb_create,
    .gem_prime_import_sg_table = drm_gem_shmem_prime_import_sg_table,
    .gem_prime_import = tzx_prime_import,
    .gem_create_object = tzx_gem_create,
    DRM_FBDEV_SHMEM_DRIVER_OPS,
};
static void release_display(void)
{
    if (drm_registered) {
        drm_dev_unregister(&display->drm);
        drm_atomic_helper_shutdown(&display->drm);
    }
    screen_vblank_cleanup();
    /* devm releases DRM resources when the DE platform device unregisters. */
    if (hardware_started) release_all();
    if (panel_started) tzx_panel_exit();
}
static int __init tzx_display_init(void)
{
    static const u32 formats[] = {DRM_FORMAT_XRGB8888};
    struct drm_device *drm;
    int ret;
    ret = tzx_panel_init(); if (ret) return ret; panel_started = true;
    scanout = true;
    ret = tzx_de_init(); if (ret) goto fail; hardware_started = true;
    display = devm_drm_dev_alloc(&pdev->dev, &tzx_drm_driver, struct tzx_drm, drm);
    if (IS_ERR(display)) { ret = PTR_ERR(display); display = NULL; goto fail; }
    drm = &display->drm; mutex_init(&display->update_lock);
    ret = drmm_mode_config_init(drm); if (ret) goto fail;
    /* Xorg rotates in a 1280x800 render buffer; panel timing stays fixed. */
    drm->mode_config.min_width = WIDTH; drm->mode_config.max_width = HEIGHT;
    drm->mode_config.min_height = WIDTH; drm->mode_config.max_height = HEIGHT;
    drm->mode_config.preferred_depth = 24; drm->mode_config.funcs = &config_funcs;
    ret = drm_connector_init(drm, &display->connector, &connector_funcs, DRM_MODE_CONNECTOR_DSI);
    if (ret) goto fail;
    drm_connector_helper_add(&display->connector, &connector_helpers);
    display->connector.status = connector_status_connected;
    /* Software fbcon uses this before its first rendering; Xorg receives the
     * same immutable mounting hint. Native DSI timing remains 800x1280. */
    ret = drm_connector_set_panel_orientation(&display->connector,
                                              DRM_MODE_PANEL_ORIENTATION_RIGHT_UP);
    if (ret) goto fail;
    ret = drm_simple_display_pipe_init(drm, &display->pipe, &pipe_funcs,
                                      formats, ARRAY_SIZE(formats), NULL, &display->connector);
    if (ret) goto fail;
    ret = screen_vblank_init(drm); if (ret) goto fail;
    drm_mode_config_reset(drm);
    ret = drm_dev_register(drm, 0); if (ret) goto fail; drm_registered = true;
    drm_client_setup_with_fourcc(drm, DRM_FORMAT_XRGB8888);
    dev_info(&pdev->dev, "DRM display ready, fixed 800x1280 memory scanout\n");
    return 0;
fail:
    release_display(); return ret;
}
static void __exit tzx_display_exit(void) { release_display(); }
module_init(tzx_display_init);
module_exit(tzx_display_exit);
MODULE_LICENSE("GPL");
MODULE_IMPORT_NS("DMA_BUF");
MODULE_DESCRIPTION("TZX A523 integrated DSI panel and DE350 DRM display");
