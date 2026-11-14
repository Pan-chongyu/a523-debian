// SPDX-License-Identifier: GPL-2.0-or-later
/* TZX A523 single RGB layer bring-up, alongside the held DSI diagnostic.
 * Register definitions follow Allwinner's CONFIG_ARCH_SUN55IW3 branch in
 * disp2/lowlevel_v35x/de35x/{de_top,de_ovl,de_bld,de_rtmx}.{c,h},
 * copyright 2017, 2020-2023 Allwinner Technology Co., Ltd.
 * This is a reversible test, not a DRM driver. The wrapper retains the
 * DSI module and unloads this module before stopping the display.
 */
#include <linux/module.h>
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/ioport.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/platform_device.h>
#include <linux/uaccess.h>
#include <dt-bindings/clock/sun55i-a523-ccu.h>

#define WIDTH 800
#define HEIGHT 1280
#define FB_BYTES (WIDTH * HEIGHT * 4)
#define FB_ALLOC ALIGN(FB_BYTES, PAGE_SIZE)
#define REG_BYTES 4096
#define DE_BASE 0x05000000
#define DE_SIZE 0x400000
#define OVL 0x1c1000
#define BLD 0x281000
#define SIZE_WORD (((HEIGHT - 1) << 16) | (WIDTH - 1))

static bool scanout, fixed_color;
module_param(scanout, bool, 0444);
module_param(fixed_color, bool, 0444);
static char report[512] = "not started";
#ifdef TZX_DRM_BUILD
module_param_string(de_report, report, sizeof(report), 0444);
#else
module_param_string(report, report, sizeof(report), 0444);
#endif
struct rcq_head { __le32 addr, len_hi, dirty, offset; };
struct reg_block { u32 offset, size, shadow; };
static const struct reg_block blocks[] = {
    {OVL, 0x80, 0x200}, {OVL + 0x80, 0xc, 0x280},
    {OVL + 0xe0, 0x1c, 0x2a0},
    {BLD, 0x60, 0x300}, {BLD + 0x80, 0x24, 0x380},
    {BLD + 0xa0, 0x60, 0x3c0},
    {0x285000, 0x2c, 0x440},
    {0x1c4000, 0x88, 0x480}, /* bypass scaler, retain global alpha */
    {0x1c5000, 0x58, 0x520}, {0x1c5400, 0x34, 0x580},
    {0x1c0800, 4, 0x5c0}, {0x1c8000, 4, 0x5e0},
    {0x28b000, 4, 0x600}, {0x28b100, 4, 0x620},
};
static struct platform_device *pdev;
static void __iomem *de, *ccu, *pck, *tcon, *dsi, *top;
static struct clk *clocks[2];
static unsigned int clocks_enabled;
static void *fb, *regs;
static dma_addr_t fb_dma, regs_dma;
static bool region, reset_released, active, registered, prepared;
static u32 bgr_saved, tcon_saved, jump_saved, top_route_saved;
static bool top_routed;
static DEFINE_MUTEX(fb_lock);

static void swrite(unsigned int block, unsigned int off, u32 value)
{
    *(__le32 *)(regs + blocks[block].shadow + off) = cpu_to_le32(value);
}

/* Exit HSD on a frame boundary. Keeping HSC and the panel powered permits
 * a source change without sending any panel commands or changing timings. */
static int pause_video(void)
{
    u32 value;
    writel(readl(dsi + 0x4c) | BIT(28), dsi + 0x4c);
    return readl_poll_timeout(dsi + 0x10, value, !(value & 1), 100, 60000);
}

static void resume_video(void)
{
    u32 value, saved_jump = readl(dsi + 0x48);
    writel(0x1f, dsi + 0x20);
    writel(0xf02, dsi + 0x48);
    writel(3 << 16, dsi + 0x10);
    writel((3 << 16) | 1, dsi + 0x10);
    if (readl_poll_timeout(dsi + 0x10, value, !(value & 1), 100, 40000))
        dev_warn(&pdev->dev, "HS clock restart timed out\n");
    writel(0xf, dsi + 0x20);
    writel(saved_jump, dsi + 0x48);
    writel(jump_saved, dsi + 0x4c);
    writel(3 << 16, dsi + 0x10);
    writel((3 << 16) | 1, dsi + 0x10);
}

static void fill_pattern(void)
{
    static const u32 colors[] = {0xffe63946, 0xfff4a261, 0xff2a9d8f, 0xff4361ee};
    u32 *pixels = fb;
    unsigned int x, y;
    for (y = 0; y < HEIGHT; y++)
        for (x = 0; x < WIDTH; x++) {
            u32 c = colors[(x >= WIDTH / 2) + 2 * (y >= HEIGHT / 2)];
            if (x < 12 || x >= WIDTH - 12 || y < 12 || y >= HEIGHT - 12 ||
                (x >= 390 && x < 410) || (y >= 630 && y < 650)) c = 0xffffffff;
            if (x >= 70 && x < 230 && y >= 70 && y < 230) c = 0xff000000;
            pixels[y * WIDTH + x] = c;
        }
}

static void build_registers(void)
{
    struct rcq_head *heads = regs;
    unsigned int i;
    for (i = 0; i < ARRAY_SIZE(blocks); i++) {
        dma_addr_t addr = regs_dma + blocks[i].shadow;
        heads[i].addr = cpu_to_le32(lower_32_bits(addr));
        heads[i].len_hi = cpu_to_le32(blocks[i].size | (upper_32_bits(addr) << 24));
        heads[i].dirty = cpu_to_le32(1);
        heads[i].offset = cpu_to_le32(blocks[i].offset);
    }
    /* XRGB8888, global alpha, opaque single layer. Disable the other layers. */
    swrite(0, 0, 1 | (1 << 1) | (4 << 8) | (0xffU << 24));
    swrite(0, 4, SIZE_WORD); swrite(0, 0xc, WIDTH * 4);
    swrite(0, 0x10, lower_32_bits(fb_dma));
    swrite(1, 0, upper_32_bits(fb_dma)); swrite(1, 8, SIZE_WORD);
    swrite(3, 0, BIT(8) | (fixed_color ? BIT(0) : 0));
    swrite(3, 4, 0xff00ff00); swrite(3, 8, SIZE_WORD);
    swrite(4, 0, 0); swrite(4, 8, 0xff101010);
    swrite(4, 0xc, SIZE_WORD); swrite(4, 0x10, 0x03010301);
    swrite(7, 0x44, 0xff);
    dma_wmb();
}

static int start_scanout(void)
{
    u32 value, version = readl(de + 0x8014);
    int ret;
    if (((version >> 16) & 0xffff) != 0x350) {
        dev_err(&pdev->dev, "unexpected DE version %08x\n", version);
        return -ENODEV;
    }
    tcon_saved = readl(tcon + 0x40); jump_saved = readl(dsi + 0x4c);
    if ((tcon_saved & 7) != 1 || !(tcon_saved & BIT(31)) ||
        !(readl(dsi + 0x10) & 1)) return -EBUSY;
    build_registers();
    top_route_saved = readl(top + 0x1c);
    writel((top_route_saved & ~0xffU) | 0xf1, top + 0x1c);
    top_routed = true;
    /* Top MMIO uses A523/DE350 routing, not the DE352/sun60iw2 layout. */
    writel(BIT(16) | BIT(0), de + 0x8004);
    writel(BIT(16) | BIT(0), de + 0x8000);
    writel(1, de + 0x8008);
    writel((readl(de + 0x8024) & ~(3U << 16)), de + 0x8024);
    writel((readl(de + 0x8028) & ~15U) | 8, de + 0x8028);
    writel((readl(de + 0x8010) & ~0xffU) | 0xf1, de + 0x8010);
    /* DE version 03500200 identifies revision 2 on this board. */
    writel((version & 0xffff) < 0x200 ? 0x10 : 0, de + 0x804c);
    writel(0x6000, de + 0x8050);
    writel(SIZE_WORD, de + 0x8108);
    writel(1, de + 0x810c);
    writel(lower_32_bits(regs_dma), de + 0x8114);
    writel(upper_32_bits(regs_dma), de + 0x8118);
    writel(ARRAY_SIZE(blocks) * sizeof(struct rcq_head), de + 0x811c);
    writel(BIT(0) | BIT(6) | BIT(7), de + 0x8100);
    prepared = true;
    /* TCON continues generating the established frame cadence while its
     * internal pattern is selected. Arm during active scan, as in the BSP. */
    ret = readl_poll_timeout(tcon + 0xfc, value,
                            ((value >> 16) & 0x1fff) > 100, 20, 50000);
    if (ret) return ret;
    writel(BIT(0) | BIT(2) | BIT(3), de + 0x8104);
    writel(1, de + 0x8110);
    ret = readl_poll_timeout(de + 0x8104, value, value & BIT(2), 100, 100000);
    dev_info(&pdev->dev, "RCQ ret=%d status=%08x ovl=%08x/%08x bld=%08x/%08x\n",
             ret, value, readl(de + OVL), readl(de + OVL + 0x10),
             readl(de + BLD), readl(de + BLD + 0x8c));
    if (ret) return ret;
    ret = pause_video();
    if (ret) { resume_video(); return ret; }
    writel(tcon_saved & ~7U, tcon + 0x40);
    active = true;
    resume_video();
    msleep(100);
    return 0;
}

static ssize_t pixel_write(struct file *file, const char __user *buf, size_t len, loff_t *pos)
{
    if (*pos < 0 || *pos >= FB_BYTES) return -ENOSPC;
    len = min_t(size_t, len, FB_BYTES - *pos);
    mutex_lock(&fb_lock);
    if (copy_from_user(fb + *pos, buf, len)) { mutex_unlock(&fb_lock); return -EFAULT; }
    dma_wmb(); *pos += len;
    mutex_unlock(&fb_lock);
    return len;
}
static loff_t pixel_seek(struct file *file, loff_t off, int whence)
{ return fixed_size_llseek(file, off, whence, FB_BYTES); }
static const struct file_operations pixel_ops = {
    .owner = THIS_MODULE, .write = pixel_write, .llseek = pixel_seek,
};
static struct miscdevice pixel_device = {
    .minor = MISC_DYNAMIC_MINOR, .name = "tzx-pixels", .fops = &pixel_ops, .mode = 0600,
};

static void release_all(void)
{
    if (registered) misc_deregister(&pixel_device);
    if (active) {
        int ret = pause_video();
        if (ret) dev_warn(&pdev->dev, "frame exit %d; restoring pattern before DE reset\n", ret);
        writel(tcon_saved, tcon + 0x40);
        resume_video();
        msleep(50);
    }
    if (prepared) {
        writel(0, de + 0x8110); writel(0, de + 0x8100);
        writel(0, de + 0x8008); writel(0, de + 0x8000);
    }
    if (top_routed) writel(top_route_saved, top + 0x1c);
    /* Reset the entire DE before freeing anything it could DMA-read. */
    if (reset_released) {
        writel(readl(ccu + 0x60c) & ~BIT(16), ccu + 0x60c);
        readl(ccu + 0x60c); udelay(10);
    }
    while (clocks_enabled) clk_disable_unprepare(clocks[--clocks_enabled]);
    if (reset_released)
        writel((readl(ccu + 0x60c) & ~BIT(16)) | (bgr_saved & BIT(16)), ccu + 0x60c);
    if (regs) dma_free_coherent(&pdev->dev, REG_BYTES, regs, regs_dma);
    if (fb) dma_free_coherent(&pdev->dev, FB_ALLOC, fb, fb_dma);
    for (unsigned int i = 0; i < ARRAY_SIZE(clocks); i++) if (clocks[i]) clk_put(clocks[i]);
    if (dsi) iounmap(dsi);
    if (tcon) iounmap(tcon);
    if (top) iounmap(top);
    if (pck) iounmap(pck);
    if (ccu) iounmap(ccu);
    if (de) iounmap(de);
    if (region) release_mem_region(DE_BASE, DE_SIZE);
    if (pdev) platform_device_unregister(pdev);
}

static int __init tzx_de_init(void)
{
    struct device_node *node;
    const unsigned int ids[] = {CLK_BUS_DE, CLK_DE};
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523")) return -ENODEV;
    pdev = platform_device_register_simple("tzx-de-scanout", -1, NULL, 0);
    if (IS_ERR(pdev)) { ret = PTR_ERR(pdev); pdev = NULL; return ret; }
    pdev->dev.dma_mask = &pdev->dev.coherent_dma_mask;
    ret = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32));
    if (ret) goto fail;
    ccu = ioremap(0x02001000, 4096); pck = ioremap(0x07060000, 0x8000);
    tcon = ioremap(0x05502000, 4096); dsi = ioremap(0x05508000, 4096);
    top = ioremap(0x05500000, 4096);
    if (!ccu || !pck || !tcon || !dsi || !top) { ret = -ENOMEM; goto fail; }
    if ((readl(pck + 0x5008) & 15) != 8) { ret = -EHOSTDOWN; goto fail; }
    bgr_saved = readl(ccu + 0x60c);
    if (bgr_saved & (BIT(16) | BIT(0))) { ret = -EBUSY; goto fail; }
    if (!request_mem_region(DE_BASE, DE_SIZE, "tzx-de-scanout")) { ret = -EBUSY; goto fail; }
    region = true; de = ioremap(DE_BASE, DE_SIZE);
    if (!de) { ret = -ENOMEM; goto fail; }
    fb = dma_alloc_coherent(&pdev->dev, FB_ALLOC, &fb_dma, GFP_KERNEL);
    regs = dma_alloc_coherent(&pdev->dev, REG_BYTES, &regs_dma, GFP_KERNEL);
    if (!fb || !regs) { ret = -ENOMEM; goto fail; }
    fill_pattern();
    node = of_find_node_by_path("/soc/clock-controller@2001000");
    if (!node) { ret = -ENODEV; goto fail; }
    for (unsigned int i = 0; i < ARRAY_SIZE(ids); i++) {
        struct of_phandle_args spec = {.np = node, .args_count = 1, .args = {ids[i]}};
        clocks[i] = of_clk_get_from_provider(&spec);
        if (IS_ERR(clocks[i])) { ret = PTR_ERR(clocks[i]); clocks[i] = NULL; of_node_put(node); goto fail; }
    }
    of_node_put(node);
    for (; clocks_enabled < ARRAY_SIZE(clocks); clocks_enabled++) {
        ret = clk_prepare_enable(clocks[clocks_enabled]); if (ret) goto fail;
    }
    writel(readl(ccu + 0x60c) | BIT(16), ccu + 0x60c); reset_released = true;
    udelay(100);
    dev_info(&pdev->dev, "DE=%08x DMA=%pad/%pad bytes=%u clk=%lu/%lu\n",
             readl(de + 0x8014), &fb_dma, &regs_dma, FB_BYTES,
             clk_get_rate(clocks[0]), clk_get_rate(clocks[1]));
    if (scanout) { ret = start_scanout(); if (ret) goto fail; }
#ifndef TZX_DRM_BUILD
    ret = misc_register(&pixel_device); if (ret) goto fail; registered = true;
#endif
    snprintf(report, sizeof(report), "active=%u DE=%08x fb=%pad regs=%pad rcq=%08x ovl=%08x/%08x bld=%08x dsi=%08x/%08x",
             active, readl(de + 0x8014), &fb_dma, &regs_dma, readl(de + 0x8104),
             readl(de + OVL), readl(de + OVL + 0x10), readl(de + BLD),
             readl(dsi + 0xfc), readl(dsi + 0x2f0));
    return 0;
fail:
    dev_err(&pdev->dev, "bring-up failed %d\n", ret); release_all(); return ret;
}
#ifndef TZX_DRM_BUILD
static void __exit tzx_de_exit(void) { release_all(); }
module_init(tzx_de_init);
module_exit(tzx_de_exit);
#endif
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX A523 reversible DE350 single-plane memory scanout test");
#ifndef TZX_DRM_BUILD
MODULE_SOFTDEP("pre: tzx_dsi_probe");
#endif
