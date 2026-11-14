/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Temporary 800x1280 TCON1 color-bar path. Register layouts and packet
 * calculations follow Allwinner de_lcd{,_type}.{c,h}/de_dsi{,_type}.{c,h},
 * copyright 2016, 2020-2023 Allwinner Technology Co., Ltd.
 * No DE, framebuffer memory, panel gamma, GIP, or bias voltage programming.
 */
static bool video, fifo_bist, hv_mode, bsp_tcon;
module_param(video, bool, 0444);
module_param(fifo_bist, bool, 0444);
module_param(hv_mode, bool, 0444);
module_param(bsp_tcon, bool, 0444);
static unsigned int htotal = 960, hbp = 88, hsync = 4;
static unsigned int vtotal = 1300, vbp = 12, vsync = 4;
static unsigned int test_pattern = 1;
module_param(htotal, uint, 0444);
module_param(hbp, uint, 0444);
module_param(hsync, uint, 0444);
module_param(vtotal, uint, 0444);
module_param(vbp, uint, 0444);
module_param(vsync, uint, 0444);
module_param(test_pattern, uint, 0444);
static void __iomem *tcon, *display_top;
static struct clk *video_clocks[3];
static unsigned int video_enabled;
static const u16 tcon_offsets[] = {
    0x00, 0x04, 0x10, 0x3c, 0x40, 0x44, 0x48, 0x4c, 0x50, 0x54,
    0x58, 0x60, 0x88, 0x8c, 0xf8, 0x160, 0x164, 0x168, 0x16c, 0x1f0, 0x230, 0x234
};
static const u16 top_offsets[] = {0x04, 0x0c, 0x20};
static u32 tcon_saved[ARRAY_SIZE(tcon_offsets)], top_saved[ARRAY_SIZE(top_offsets)];
static u32 tcon_reset_saved, top_reset_saved;
static bool tcon_region, top_region, video_reset_changed, video_saved;

static u32 video_header(u8 kind, unsigned int bytes)
{
    u32 header = kind | (vc << 6) | (bytes << 8);
    return header | ((u32)header_ecc(header) << 24);
}

static u16 zero_crc(unsigned int bytes)
{
    u16 crc = 0xffff;
    while (bytes--)
        for (unsigned int bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ ((crc & 1) ? 0x8408 : 0);
    return crc;
}

static int prepare_video(void)
{
    const unsigned int ids[] = {CLK_BUS_DISPLAY0_TOP, CLK_BUS_TCON_LCD1, CLK_TCON_LCD1};
    struct device_node *node;
    int ret;
    if (htotal < 880 || htotal > 1100 || hbp < hsync + 2 || hbp + 20 >= htotal - 800 ||
        hsync < 4 || hsync > 40 || vtotal < 1296 || vtotal > 1400 ||
        vbp < vsync || vbp > vtotal - 1280 || vsync < 1 || vsync > 10 ||
        (test_pattern != 1 && test_pattern != 2 && test_pattern != 3 &&
         test_pattern != 4 && test_pattern != 5 && test_pattern != 7))
        return -EINVAL;
    tcon_reset_saved = readl(ccu + 0xb7c);
    top_reset_saved = readl(ccu + 0xabc);
    if ((tcon_reset_saved & (BIT(17) | BIT(1))) ||
        (top_reset_saved & (BIT(16) | BIT(0)))) return -EBUSY;
    if (!request_mem_region(0x05502000, 0x1000, "tzx-tcon1-color-test")) return -EBUSY;
    tcon_region = true;
    if (!request_mem_region(0x05500000, 0x1000, "tzx-display-top-test")) return -EBUSY;
    top_region = true;
    tcon = ioremap(0x05502000, 0x1000);
    display_top = ioremap(0x05500000, 0x1000);
    if (!tcon || !display_top) return -ENOMEM;
    node = of_find_node_by_path("/soc/clock-controller@2001000");
    if (!node) return -ENODEV;
    for (unsigned int i = 0; i < ARRAY_SIZE(ids); i++) {
        struct of_phandle_args spec = {.np = node, .args_count = 1, .args = {ids[i]}};
        video_clocks[i] = of_clk_get_from_provider(&spec);
        if (IS_ERR(video_clocks[i])) {
            ret = PTR_ERR(video_clocks[i]); video_clocks[i] = NULL;
            of_node_put(node); return ret;
        }
    }
    of_node_put(node);
    for (; video_enabled < ARRAY_SIZE(ids); video_enabled++) {
        ret = clk_prepare_enable(video_clocks[video_enabled]);
        if (ret) return ret;
    }
    writel(readl(ccu + 0xabc) | BIT(16), ccu + 0xabc);
    writel(readl(ccu + 0xb7c) | BIT(17), ccu + 0xb7c);
    video_reset_changed = true;
    usleep_range(100, 200);
    for (unsigned int i = 0; i < ARRAY_SIZE(tcon_offsets); i++)
        tcon_saved[i] = readl(tcon + tcon_offsets[i]);
    for (unsigned int i = 0; i < ARRAY_SIZE(top_offsets); i++)
        top_saved[i] = readl(display_top + top_offsets[i]);
    video_saved = true;
    /* Current BSP uses LS=HS/6; retain HS/4 only for the older experiment. */
    writel(readl(display_top + 0x0c) | BIT(1) | BIT(5), display_top + 0x0c);
    writel(readl(display_top + 0x04) & ~BIT(4), display_top + 0x04);
    writel(readl(display_top + 0x20) | BIT(17), display_top + 0x20);
    writel(0, tcon + 0x00); writel(0, tcon + 0x04);
    writel(0, tcon + 0x10); /* no dithering */
    /* Current DRM BSP leaves single-DSI 3D FIFO at reset, unlike disp2. */
    writel(bsp_tcon ? 0 : 1, tcon + 0x3c);
    writel(test_pattern | (2U << 4) | (hv_mode ? 0 : BIT(24)), tcon + 0x40);
    writel(1, tcon + 0x44); /* DCLK /1; enabled after packet setup */
    writel(((800 - 1) << 16) | (1280 - 1), tcon + 0x48);
    writel(((htotal - 1) << 16) | (hbp - 1), tcon + 0x4c);
    writel(((vtotal * 2) << 16) | (vbp - 1), tcon + 0x50);
    writel(((hsync - 1) << 16) | (vsync - 1), tcon + 0x54);
    writel(0, tcon + 0x58);
    writel(0, tcon + 0x88); writel(0xe0000000, tcon + 0x8c);
    writel(8, tcon + 0xf8);
    /* DRM BSP uses dsi_div=6, LS=pixel clock, and TCON DCLK /1. */
    writel(((htotal * 24 / ((bsp_tcon ? 6 : 4) * 4) - 800 - 40) << 16) | (800 - 1), tcon + 0x160);
    writel(1280 - 1, tcon + 0x164);
    writel(((bsp_tcon ? (3 * htotal / 8 - 1) :
             (10 * htotal * 300 / (hs_rate / 6000000) / 8)) << 16) | 10, tcon + 0x168);
    writel(0, tcon + 0x16c); writel(0, tcon + 0x230); writel(0, tcon + 0x234);
    if (bsp_tcon) writel(((hs_rate / 6000000 * 15) << 16) | 3, tcon + 0x1f0);
    writel(hv_mode ? 0 : (BIT(28) | BIT(16) | BIT(2) | BIT(0)), tcon + 0x60);
    pr_info("TZX DSI: TCON1 prepared 800x1280 totals=%u,%u mode=%s CCF=%lu,%lu,%lu top=%08x\n",
            htotal, vtotal, hv_mode ? "HV" : "CPU trigger", clk_get_rate(video_clocks[0]),
            clk_get_rate(video_clocks[1]), clk_get_rate(video_clocks[2]), readl(display_top + 0x0c));
    return 0;
}

static void start_video(void)
{
    unsigned int hsa = hsync * 3 - 10, hback = (hbp - hsync) * 3 - 6;
    unsigned int hblank = (htotal - hsync) * 3 - 10;
    unsigned int hfront = hblank - (4 + 800 * 3 + 2) - (4 + hback + 2);
    unsigned int vblank = 4 - ((htotal * 3 * vtotal - (4 + hblank + 2)) % 4);
    const u16 blank_offsets[] = {0xc0, 0xc8, 0xd0, 0xe0, 0xe8};
    const unsigned int sizes[] = {hsa, hback, hfront, hblank, vblank};
    writel(3 << 16, host + 0x10);
    writel(0, host + 0x0c); writel(0x17, host + 0x14);
    writel(((vbp - vsync) << 16) | vsync, host + 0x18);
    writel((vtotal << 16) | 1280, host + 0x1c);
    writel(0x0f, host + 0x20); writel(0x20000010, host + 0x28);
    writel(0x2000000f, host + 0x2c); /* HSD, pixel packet on all data lanes */
    writel(0x40000010, host + 0x34); writel(0x0f, host + 0x38);
    writel(0x5000001f, host + 0x3c);
    writel((49U << 16) | 49, host + 0x44);
    writel((49U << 16) | 49, host + 0x54);
    writel((5U << 20) | (6U << 16) | 1, host + 0x4c);
    writel(BIT(28) | ((htotal - 800 - hbp - 20) * 3 / 4), host + 0x7c);
    writel(BIT(16) | 8, host + 0x80);
    writel(video_header(0x3e, 800 * 3), host + 0x90);
    writel(0xffff, host + 0x98); writel(0xffffffff, host + 0x9c);
    for (unsigned int i = 0; i < 4; i++)
        writel(video_header((u8[]){0x21, 0x31, 0x01, 0x11}[i], 0), host + 0xb0 + i * 4);
    for (unsigned int i = 0; i < ARRAY_SIZE(sizes); i++) {
        writel(video_header(0x19, sizes[i]), host + blank_offsets[i]);
        writel((u32)zero_crc(sizes[i]) << 16, host + blank_offsets[i] + 4);
    }
    writel(fifo_bist ? (BIT(28) | 0xffffff) : 0xff, host + 0x2f8);
    writel(readl(tcon + 0x40) | BIT(31), tcon + 0x40);
    writel(BIT(31), tcon + 0x00);
    writel(0xf0000001, tcon + 0x44);
    /* Clock already runs: LP11 -> NOP -> HSD -> DLY -> NOP ... */
    writel(6 | (3U << 24) | (7U << 12) | (6U << 28) | (15U << 20), host + 0x48);
    writel((3 << 16) | 1, host + 0x10);
    msleep(100);
    pr_info("TZX DSI: video started bist=%d line=%08x fifo=%08x inst=%08x tcon=%08x\n",
            fifo_bist, readl(host + 0x2e0), readl(host + 0x2f4),
            readl(host + 0x2f0), readl(tcon + 0xfc));
}

static void release_video(void)
{
    if (video_saved) {
        writel(3 << 16, host + 0x10);
        writel(0, tcon + 0x00); writel(0, tcon + 0x40); writel(1, tcon + 0x44);
        for (unsigned int i = 0; i < ARRAY_SIZE(tcon_offsets); i++)
            writel(tcon_saved[i], tcon + tcon_offsets[i]);
        for (unsigned int i = 0; i < ARRAY_SIZE(top_offsets); i++)
            writel(top_saved[i], display_top + top_offsets[i]);
    }
    if (video_reset_changed) {
        writel((readl(ccu + 0xb7c) & ~BIT(17)) | (tcon_reset_saved & BIT(17)), ccu + 0xb7c);
        writel((readl(ccu + 0xabc) & ~BIT(16)) | (top_reset_saved & BIT(16)), ccu + 0xabc);
    }
    while (video_enabled) clk_disable_unprepare(video_clocks[--video_enabled]);
    for (unsigned int i = 0; i < ARRAY_SIZE(video_clocks); i++)
        if (video_clocks[i]) clk_put(video_clocks[i]);
    if (display_top) iounmap(display_top);
    if (tcon) iounmap(tcon);
    if (top_region) release_mem_region(0x05500000, 0x1000);
    if (tcon_region) release_mem_region(0x05502000, 0x1000);
}
