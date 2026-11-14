// SPDX-License-Identifier: GPL-2.0-or-later
/* A523 DSI1 video-vblank interrupt observation. Allwinner BSP GINT0 uses
 * enables in low16 and W1C flags in high16; DSI_IRQ_VIDEO_VBLK is bit2.
 * A523 vendor DT routes DSI1 to GIC SPI95. The link keeps scanning unchanged.
 */
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/irqdomain.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/of.h>

static void __iomem *host_regs;
static int frame_irq;
static bool requested;
static u32 saved_enable;
static unsigned long frame_irqs;
static unsigned long period_min_us = ULONG_MAX, period_max_us;
static unsigned long irq_storm;
static ktime_t last, started;
module_param(frame_irqs, ulong, 0444);
module_param(period_min_us, ulong, 0444);
module_param(period_max_us, ulong, 0444);
module_param(irq_storm, ulong, 0444);

static irqreturn_t frame_interrupt(int irq, void *cookie)
{
    u32 value = readl(host_regs + 4);
    ktime_t now;
    s64 period;
    if (!(value & BIT(18)) || !(value & BIT(2))) return IRQ_NONE;
    writel((value & 0xffff) | BIT(18), host_regs + 4);
    now = ktime_get();
    if (frame_irqs) {
        period = ktime_us_delta(now, last);
        if (period >= 0) {
            period_min_us = min_t(unsigned long, period_min_us, period);
            period_max_us = max_t(unsigned long, period_max_us, period);
        }
    }
    last = now;
    frame_irqs++;
    if (frame_irqs > 1000 && ktime_ms_delta(now, started) < 500) {
        irq_storm = 1;
        writel((readl(host_regs + 4) & 0xffff) & ~BIT(2), host_regs + 4);
    }
    return IRQ_HANDLED;
}

static int __init begin(void)
{
    struct device_node *gic;
    struct irq_fwspec spec = { .param_count = 3, .param = {0, 95, IRQ_TYPE_LEVEL_HIGH} };
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523")) return -ENODEV;
    host_regs = ioremap(0x05508000, 4096);
    if (!host_regs) return -ENOMEM;
    if (!(readl(host_regs + 0x10) & BIT(0)) ||
        readl(host_regs + 0x1c) != ((1303U << 16) | 1280)) {
        ret = -ENODEV; goto fail;
    }
    saved_enable = readl(host_regs + 4) & 0xffff;
    if (saved_enable) { ret = -EBUSY; goto fail; }
    gic = of_find_compatible_node(NULL, NULL, "arm,gic-v3");
    if (!gic) { ret = -ENODEV; goto fail; }
    spec.fwnode = of_fwnode_handle(gic);
    frame_irq = irq_create_fwspec_mapping(&spec);
    of_node_put(gic);
    if (!frame_irq || irq_get_irq_data(frame_irq)->hwirq != 127) {
        ret = -ENODEV; goto fail;
    }
    started = ktime_get();
    ret = request_irq(frame_irq, frame_interrupt, 0, "tzx-dsi-frame-probe", &frame_irq);
    if (ret) goto fail;
    requested = true;
    writel(BIT(18) | BIT(2), host_regs + 4);
    pr_info("TZX_DSI_FRAME_PROBE_ARMED irq=%d GIC_SPI=95\n", frame_irq);
    return 0;
fail:
    iounmap(host_regs); host_regs = NULL;
    return ret;
}

static void __exit end(void)
{
    if (requested) {
        writel(saved_enable | BIT(18), host_regs + 4);
        free_irq(frame_irq, &frame_irq);
    }
    pr_info("TZX_DSI_FRAME_PROBE_STOP count=%lu min=%lu max=%lu storm=%lu\n",
            frame_irqs, period_min_us, period_max_us, irq_storm);
    iounmap(host_regs);
}
module_init(begin);
module_exit(end);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX A523 bounded DSI video frame interrupt observation");
