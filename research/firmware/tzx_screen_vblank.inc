/* SPDX-License-Identifier: GPL-2.0-or-later */
/* The observed DSI1 VIDEO_VBLK interrupt is the panel's frame boundary.
 * Allwinner GINT0: low16 enables, high16 W1C flags, video-vblank bit2.
 */
#include <linux/interrupt.h>
#include <linux/irqdomain.h>
#include <drm/drm_vblank.h>

static int screen_frame_irq;
static bool screen_irq_requested;
static DEFINE_SPINLOCK(screen_irq_lock);
static unsigned long screen_vblank_events;
module_param(screen_vblank_events, ulong, 0444);

static int screen_enable_vblank(struct drm_simple_display_pipe *pipe)
{
    unsigned long flags;
    u32 enables;
    spin_lock_irqsave(&screen_irq_lock, flags);
    enables = readl(dsi + 4) & 0xffff;
    writel(enables | BIT(2) | BIT(18), dsi + 4);
    spin_unlock_irqrestore(&screen_irq_lock, flags);
    return 0;
}

static void screen_disable_vblank(struct drm_simple_display_pipe *pipe)
{
    unsigned long flags;
    u32 enables;
    spin_lock_irqsave(&screen_irq_lock, flags);
    enables = readl(dsi + 4) & 0xffff;
    writel((enables & ~BIT(2)) | BIT(18), dsi + 4);
    spin_unlock_irqrestore(&screen_irq_lock, flags);
}

static irqreturn_t screen_vblank_interrupt(int irq, void *cookie)
{
    unsigned long flags;
    u32 status;
    spin_lock_irqsave(&screen_irq_lock, flags);
    status = readl(dsi + 4);
    if (!(status & BIT(2)) || !(status & BIT(18))) {
        spin_unlock_irqrestore(&screen_irq_lock, flags);
        return IRQ_NONE;
    }
    writel((status & 0xffff) | BIT(18), dsi + 4);
    screen_vblank_events++;
    spin_unlock_irqrestore(&screen_irq_lock, flags);
    drm_crtc_handle_vblank(&display->pipe.crtc);
    return IRQ_HANDLED;
}

static int screen_vblank_init(struct drm_device *drm)
{
    struct device_node *gic;
    struct irq_fwspec spec = { .param_count = 3, .param = {0, 95, IRQ_TYPE_LEVEL_HIGH} };
    int ret;
    if (readl(dsi + 4) & 0xffff) return -EBUSY;
    ret = drm_vblank_init(drm, 1);
    if (ret) return ret;
    gic = of_find_compatible_node(NULL, NULL, "arm,gic-v3");
    if (!gic) return -ENODEV;
    spec.fwnode = of_fwnode_handle(gic);
    screen_frame_irq = irq_create_fwspec_mapping(&spec);
    of_node_put(gic);
    if (!screen_frame_irq || !irq_get_irq_data(screen_frame_irq) ||
        irq_get_irq_data(screen_frame_irq)->hwirq != 127)
        return -ENODEV;
    ret = request_irq(screen_frame_irq, screen_vblank_interrupt, 0, "tzx-dsi-vblank", display);
    if (!ret) screen_irq_requested = true;
    return ret;
}

static void screen_vblank_cleanup(void)
{
    if (!screen_irq_requested) return;
    screen_disable_vblank(&display->pipe);
    free_irq(screen_frame_irq, display);
    screen_irq_requested = false;
}

static void screen_send_event(struct drm_simple_display_pipe *pipe)
{
    struct drm_crtc *crtc = &pipe->crtc;
    struct drm_pending_vblank_event *event = crtc->state->event;
    unsigned long flags;
    int ret;
    if (!event) return;
    ret = drm_crtc_vblank_get(crtc);
    spin_lock_irqsave(&crtc->dev->event_lock, flags);
    crtc->state->event = NULL;
    if (ret) drm_crtc_send_vblank_event(crtc, event);
    else drm_crtc_arm_vblank_event(crtc, event);
    spin_unlock_irqrestore(&crtc->dev->event_lock, flags);
}
