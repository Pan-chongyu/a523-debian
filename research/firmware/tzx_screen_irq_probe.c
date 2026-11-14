// SPDX-License-Identifier: GPL-2.0-or-later
/* Bounded observation of the A523 TCON-LCD1 CPU-trigger frame interrupt.
 * BSP: TCON0_CNTR=10, GINT0 flags low16/write-zero-clear, enables high16.
 * A523 vendor DT: TCON-LCD1 is GIC SPI 92. No display timing changes.
 */
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/irqdomain.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/of.h>

static void __iomem *tcon_regs;
static int screen_irq;
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

static irqreturn_t screen_interrupt(int irq, void *cookie)
{
    u32 value = readl(tcon_regs + 4);
    ktime_t now;
    s64 period;
    if (!(value & BIT(10)) || !(value & BIT(26))) return IRQ_NONE;
    writel(value & ~BIT(10), tcon_regs + 4);
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
        writel(readl(tcon_regs + 4) & ~BIT(26), tcon_regs + 4);
    }
    return IRQ_HANDLED;
}

static int __init begin(void)
{
    struct device_node *gic;
    struct irq_fwspec spec = { .param_count = 3, .param = {0, 92, IRQ_TYPE_LEVEL_HIGH} };
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523")) return -ENODEV;
    tcon_regs = ioremap(0x05502000, 4096);
    if (!tcon_regs) return -ENOMEM;
    if (!(readl(tcon_regs) & BIT(31)) ||
        readl(tcon_regs + 0x48) != ((799U << 16) | 1279)) {
        ret = -ENODEV; goto fail;
    }
    saved_enable = readl(tcon_regs + 4) & 0xffff0000;
    if (saved_enable) { ret = -EBUSY; goto fail; }
    gic = of_find_compatible_node(NULL, NULL, "arm,gic-v3");
    if (!gic) { ret = -ENODEV; goto fail; }
    spec.fwnode = of_fwnode_handle(gic);
    screen_irq = irq_create_fwspec_mapping(&spec);
    of_node_put(gic);
    if (!screen_irq || irq_get_irq_data(screen_irq)->hwirq != 124) {
        ret = -ENODEV; goto fail;
    }
    started = ktime_get();
    ret = request_irq(screen_irq, screen_interrupt, 0, "tzx-screen-frame-probe", &screen_irq);
    if (ret) goto fail;
    requested = true;
    writel((readl(tcon_regs + 4) & 0xffff & ~BIT(10)) | BIT(26), tcon_regs + 4);
    pr_info("TZX_SCREEN_FRAME_PROBE_ARMED irq=%d GIC_SPI=92\n", screen_irq);
    return 0;
fail:
    iounmap(tcon_regs); tcon_regs = NULL;
    return ret;
}

static void __exit end(void)
{
    if (requested) {
        writel((readl(tcon_regs + 4) & 0xffff & ~BIT(10)) | saved_enable, tcon_regs + 4);
        free_irq(screen_irq, &screen_irq);
    }
    pr_info("TZX_SCREEN_FRAME_PROBE_STOP count=%lu min=%lu max=%lu storm=%lu\n",
            frame_irqs, period_min_us, period_max_us, irq_storm);
    iounmap(tcon_regs);
}
module_init(begin);
module_exit(end);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX A523 bounded TCON frame interrupt observation");
