// SPDX-License-Identifier: GPL-2.0-only
/* Reversible DSI1 diagnostic; optional TCON color bars, no vendor panel init.
 * Classic LP instruction sequence follows Allwinner's de_dsi.c (GPL-2.0+).
 * The guarded userspace wrapper owns temporary panel rail enables.
 */
#include <linux/clk.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio/machine.h>
#include <linux/ioport.h>
#include <linux/of_clk.h>
#include <linux/platform_device.h>
#include <dt-bindings/clock/sun55i-a523-ccu.h>
#include "tzx_dsi_phy.h"

static bool probe_panel;
module_param(probe_panel, bool, 0444);
static unsigned int vc;
module_param(vc, uint, 0444);
static unsigned long hs_rate = 432000000;
module_param(hs_rate, ulong, 0444);
static bool wake_panel, backlight, hold, dump_regs, hs_clock, pwm_backlight, bias;
static bool bsp_analog, bsp_pll, all_pixels_test;
module_param(wake_panel, bool, 0444);
module_param(backlight, bool, 0444);
module_param(hold, bool, 0444);
module_param(dump_regs, bool, 0444);
module_param(hs_clock, bool, 0444);
module_param(pwm_backlight, bool, 0444);
module_param(bias, bool, 0444);
module_param(bsp_analog, bool, 0444);
module_param(bsp_pll, bool, 0444);
module_param(all_pixels_test, bool, 0444);
static unsigned int duty = 20;
module_param(duty, uint, 0444);
static char report[512] = "not run";
module_param_string(report, report, sizeof(report), 0444);

static struct gpiod_lookup_table pins = {
    .dev_id = "tzx-dsi-probe",
    .table = {
        GPIO_LOOKUP_IDX("2000000.pinctrl", 106, "lane", 0, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 107, "lane", 1, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 108, "lane", 2, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 109, "lane", 3, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 110, "lane", 4, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 111, "lane", 5, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 112, "lane", 6, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 113, "lane", 7, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 114, "lane", 8, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 115, "lane", 9, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP("2000000.pinctrl", 118, "reset", GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP("2000000.pinctrl", 119, "backlight", GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 242, "bias", 0, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 243, "bias", 1, GPIO_ACTIVE_HIGH), {}
    }
};
/* Only registers explicitly modified by the diagnostic are restored. */
static const u16 phy_offsets[] = {
    0x00, 0x04, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x4c, 0x50,
    0x54, 0x58, 0x5c, 0x104, 0x108, 0x10c, 0x110, 0x118
};
static const u16 host_offsets[] = {
    0x00, 0x04, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28,
    0x2c, 0x30, 0x34, 0x38, 0x3c, 0x40, 0x44, 0x48, 0x4c, 0x50,
    0x54, 0x60, 0x78, 0x7c, 0x80, 0x90, 0x98, 0x9c,
    0xb0, 0xb4, 0xb8, 0xbc, 0xc0, 0xc4, 0xc8, 0xcc, 0xd0, 0xd4,
    0xe0, 0xe4, 0xe8, 0xec, 0x2f8, 0x200, 0x300
};
static struct platform_device *owner;
static struct clk *clocks[3];
static struct gpio_desc *lanes[10], *reset, *bl;
static struct gpio_desc *bias_pins[2];
static void __iomem *ccu, *pio, *host, *phy;
static struct sun55i_dphy dphy = {.lanes = 4};
static u32 saved_phy[ARRAY_SIZE(phy_offsets)], saved_host[ARRAY_SIZE(host_offsets)];
static u32 saved_pd[3], reset_saved, pd_data_saved;
static u32 saved_ph_cfg, saved_ph_data;
static bool bias_saved;
static unsigned long mod_rate;
static bool lookup, saved, reset_changed, pins_saved, host_region, phy_region;
static unsigned int enabled;
static const u16 pwm_offsets[] = {0x20, 0x40, 0x80, 0x100, 0x104};
static struct clk *pwm_clock;
static void __iomem *pwm;
static u32 saved_pwm[ARRAY_SIZE(pwm_offsets)], pwm_reset_saved;
static bool pwm_region, pwm_enabled, pwm_reset_changed, pwm_saved;
static void release_probe(void);

static int enable_pwm_backlight(void)
{
    struct device_node *node;
    struct of_phandle_args spec = {.args_count = 1, .args = {CLK_BUS_PWM0}};
    int ret;
    pwm_reset_saved = readl(ccu + 0x7ac);
    if (pwm_reset_saved & (BIT(16) | BIT(0))) return -EBUSY;
    if (!request_mem_region(0x02000c00, 0x400, "tzx-backlight-pwm-test"))
        return -EBUSY;
    pwm_region = true;
    pwm = ioremap(0x02000c00, 0x400);
    if (!pwm) return -ENOMEM;
    node = of_find_node_by_path("/soc/clock-controller@2001000");
    if (!node) return -ENODEV;
    spec.np = node;
    pwm_clock = of_clk_get_from_provider(&spec);
    of_node_put(node);
    if (IS_ERR(pwm_clock)) {
        ret = PTR_ERR(pwm_clock); pwm_clock = NULL; return ret;
    }
    ret = clk_prepare_enable(pwm_clock);
    if (ret) return ret;
    pwm_enabled = true;
    writel(readl(ccu + 0x7ac) | BIT(16), ccu + 0x7ac);
    pwm_reset_changed = true;
    usleep_range(100, 200);
    if (readl(pwm + 0x80)) return -EBUSY;
    for (unsigned int i = 0; i < ARRAY_SIZE(pwm_offsets); i++)
        saved_pwm[i] = readl(pwm + pwm_offsets[i]);
    pwm_saved = true;
    /* 24 MHz HOSC, no divider: 480 ticks = 50 kHz, normal polarity. */
    writel(0, pwm + 0x20);
    writel((479U << 16) | (480U * duty / 100), pwm + 0x104);
    writel(BIT(8), pwm + 0x100);
    writel((readl(pwm + 0x40) & ~BIT(16)) | BIT(0), pwm + 0x40);
    writel(BIT(0), pwm + 0x80);
    writel((readl(pio + 0x98) & ~0xf0000000U) | 0x20000000U, pio + 0x98);
    pr_info("TZX DSI: candidate backlight PWM0 PD23 50 kHz duty=%u%% regs=%08x,%08x,%08x\n",
            duty, readl(pwm + 0x40), readl(pwm + 0x80), readl(pwm + 0x104));
    return 0;
}

static u8 header_ecc(u32 header)
{
    static const u32 masks[] = {0xf12cb7, 0xf2555b, 0x749a6d,
                                0xb8e38e, 0xdf03f0, 0xeffc00};
    u8 ecc = 0;
    for (unsigned int i = 0; i < ARRAY_SIZE(masks); i++)
        ecc |= (hweight32(header & masks[i]) & 1) << i;
    return ecc;
}

static int lp_packet(void __iomem *host, u8 type, u16 data, bool read)
{
    u32 header = type | (vc << 6) | ((u32)data << 8), value;
    /* Clear write-one-to-clear flags before each transaction. */
    writel(BIT(26) | BIT(25) | BIT(9), host + 0x200);
    writel(header | ((u32)header_ecc(header) << 24), host + 0x300);
    writel(3, host + 0x200);
    /* LP11 -> LPDT -> [DLY -> TBA] -> END. */
    writel(read ? (4 | (7U << 16) | (1U << 28) | (15U << 4)) :
                  (4 | (15U << 16)), host + 0x48);
    writel(BIT(16) | BIT(17), host + 0x10);
    writel(BIT(16) | BIT(17) | BIT(0), host + 0x10);
    int ret = readl_poll_timeout(host + 0x10, value, !(value & BIT(0)),
                                 50, 20000);
    if (ret)
        writel(BIT(16) | BIT(17), host + 0x10);
    return ret;
}

static int read_id(void __iomem *host, u8 command)
{
    u8 response[32] = {};
    u32 ctl, header;
    int tx, ret;
    unsigned int n = 0;
    tx = lp_packet(host, 0x37, 8, false);
    if (tx) {
        pr_info("TZX DSI: max-return timeout %d\n", tx);
        return tx;
    }
    ret = lp_packet(host, 0x06, command, true);
    ctl = readl(host + 0x200);
    header = readl(host + 0x240);
    /* RX flag can be unreliable on this IP; raw header is always logged. */
    if (!ret && !(ctl & BIT(26))) {
        switch (header & 0x3f) {
        case 0x21: response[0] = header >> 8; n = 1; break;
        case 0x22:
            response[0] = header >> 8; response[1] = header >> 16;
            n = 2; break;
        case 0x1c:
            n = (header >> 8) & 0xffff;
            if (n > 8 || ((ctl >> 16) & 31) + 1 < n + 6) {
                n = 0; break;
            }
            for (unsigned int i = 0; i < n; i++)
                response[i] = readl(host + 0x244 + (i & ~3)) >> (8 * (i & 3));
            break;
        }
    }
    pr_info("TZX DSI: vc=%u cmd=%02x ret=%d ctl=%08x header=%08x bytes=%u data=%*ph debug=%08x\n",
            vc, command, ret, ctl, header, n, n, response, readl(host + 0x2f0));
    return n ? response[0] : -EIO;
}

static int start_hs_clock(void)
{
    u32 value;
    writel(0x1f, host + 0x20);
    writel(0x20000010, host + 0x28);
    writel(2 | (15U << 8), host + 0x48);
    writel(BIT(16) | BIT(17), host + 0x10);
    writel(BIT(16) | BIT(17) | BIT(0), host + 0x10);
    int ret = readl_poll_timeout(host + 0x10, value, !(value & BIT(0)), 50, 20000);
    pr_info("TZX DSI: final HS clock ret=%d PHY=%08x inst=%08x\n",
            ret, readl(phy + 0xe0), readl(host + 0x2f0));
    if (ret) return ret;
    writel(0x0f, host + 0x20);
    usleep_range(1000, 1500);
    return 0;
}

#include "tzx_dsi_video.h"

static int __init tzx_dsi_init(void)
{
    const unsigned int ids[] = {CLK_BUS_MIPI_DSI1, CLK_MIPI_DSI1, CLK_COMBOPHY_DSI1};
    struct device_node *node;
    int ret = -ENODEV;
    if (!of_machine_is_compatible("tzx,p30a523") || vc > 3 ||
        hs_rate < 80000000 || hs_rate > 500000000 || duty < 1 || duty > 80 ||
        (backlight && pwm_backlight) ||
        (bsp_pll && (!video || hs_rate != 432000000)) ||
        (video && (!hs_clock || !wake_panel || !hold || !probe_panel)))
        return -EINVAL;
    owner = platform_device_register_simple("tzx-dsi-probe", -1, NULL, 0);
    if (IS_ERR(owner)) return PTR_ERR(owner);
    if (!request_mem_region(0x05508000, 0x1000, "tzx-dsi1-lp-probe")) {
        ret = -EBUSY; goto out;
    }
    host_region = true;
    if (!request_mem_region(0x05509000, 0x1000, "tzx-dsi1-phy-probe")) {
        ret = -EBUSY; goto out;
    }
    phy_region = true;
    host = ioremap(0x05508000, 0x1000);
    phy = ioremap(0x05509000, 0x1000);
    ccu = ioremap(0x02001000, 0x1000);
    pio = ioremap(0x02000000, 0x800);
    if (!host || !phy || !ccu || !pio) { ret = -ENOMEM; goto out; }
    /* A running display path would make this one-shot probe inappropriate. */
    reset_saved = readl(ccu + 0xb4c);
    if (reset_saved & (BIT(17) | BIT(1))) { ret = -EBUSY; goto out; }
    node = of_find_node_by_path("/soc/clock-controller@2001000");
    if (!node) goto out;
    for (unsigned int i = 0; i < ARRAY_SIZE(clocks); i++) {
        struct of_phandle_args spec = {.np = node, .args_count = 1, .args = {ids[i]}};
        clocks[i] = of_clk_get_from_provider(&spec);
        if (IS_ERR(clocks[i])) {
            ret = PTR_ERR(clocks[i]); clocks[i] = NULL;
            of_node_put(node); goto out;
        }
    }
    of_node_put(node);
    mod_rate = clk_get_rate(clocks[1]);
    ret = clk_set_rate(clocks[1], 150000000);
    if (ret) goto out;
    for (enabled = 0; enabled < ARRAY_SIZE(clocks); enabled++) {
        ret = clk_prepare_enable(clocks[enabled]);
        if (ret) goto out;
    }
    /* Only this disabled block's reset bit is changed. Clock gates are owned
     * by CCF; preserve all unrelated CCU bits during reset and cleanup. */
    writel(readl(ccu + 0xb4c) | BIT(17), ccu + 0xb4c);
    reset_changed = true;
    usleep_range(100, 200);
    for (unsigned int i = 0; i < ARRAY_SIZE(phy_offsets); i++)
        saved_phy[i] = readl(phy + phy_offsets[i]);
    for (unsigned int i = 0; i < ARRAY_SIZE(host_offsets); i++)
        saved_host[i] = readl(host + host_offsets[i]);
    saved = true;
    dphy.base = phy;
    dphy.hs_clk_rate = hs_rate;
    sun55i_dphy_timing(&dphy);
    sun55i_dphy_lane_set(&dphy);
    sun55i_dphy_analog_on(&dphy);
    if (bsp_analog) {
        /* A523 BSP phy1_data, against its accompanying register map. */
        writel(0x77, phy + 0x4c);
        writel(0x84363538, phy + 0x5c);
    }
    sun55i_dphy_pll_set(&dphy, hs_rate);
    if (video) {
        /* Primary BSP formulas: HS=24M*N/(P+1)/(M0+1)/(M1+1),
         * LS=24M*N/(P+1)/(M2+1)/(M3+1). The reference LP diagnostic
         * leaves M2/M3 at reset and M1=2; that is not video clocking.
         * Keep its already verified VCO, derive HS and LS coherently. */
        u32 reg = readl(phy + 0x104);
        reg &= ~(GENMASK(29, 24) | GENMASK(3, 0));
        reg |= ((hv_mode || bsp_tcon) ? 5U : 3U) << 24;
        if (bsp_pll) {
            /* A523 BSP's exact 432 MHz single-DSI factors: VCO 1728 MHz,
             * HS /4, LS /16 (CPU) or /24 (HV). */
            reg &= ~(GENMASK(19, 8) | GENMASK(5, 0) | GENMASK(29, 24));
            reg |= (72U << 8) | 3U | (3U << 28) | (((hv_mode || bsp_tcon) ? 5U : 3U) << 24);
        }
        writel(reg | BIT(31), phy + 0x104);
        /* Both mainline sun6i and the A523 BSP define CLK_CONT as bit28. */
        writel((readl(phy + 0x04) & ~BIT(26)) | BIT(28), phy + 0x04);
    }
    ret = sun55i_dphy_pll_enable(&dphy);
    snprintf(report, sizeof(report), "pll=%d dbg0=%08x pll0=%08x pll1=%08x panel=%d",
             ret, readl(phy + 0xe0), readl(phy + 0x104), readl(phy + 0x108), probe_panel);
    pr_info("TZX DSI: %s clocks=%lu,%lu,%lu\n", report,
            clk_get_rate(clocks[0]), clk_get_rate(clocks[1]), clk_get_rate(clocks[2]));
    if (ret || !probe_panel) goto out;
    for (unsigned int i = 0; i < 3; i++) saved_pd[i] = readl(pio + 0x90 + i * 4);
    pd_data_saved = readl(pio + 0xa0);
    pins_saved = true;
    gpiod_add_lookup_table(&pins); lookup = true;
    for (unsigned int i = 0; i < ARRAY_SIZE(lanes); i++) {
        lanes[i] = gpiod_get_index(&owner->dev, "lane", i, GPIOD_ASIS);
        if (IS_ERR(lanes[i])) { ret = PTR_ERR(lanes[i]); lanes[i] = NULL; goto out; }
    }
    reset = gpiod_get(&owner->dev, "reset", GPIOD_ASIS);
    if (IS_ERR(reset)) { ret = PTR_ERR(reset); reset = NULL; goto out; }
    ret = gpiod_direction_output(reset, 0);
    if (ret) goto out;
    if (bias) {
        saved_ph_cfg = readl(pio + 0x158);
        saved_ph_data = readl(pio + 0x160);
        bias_saved = true;
        for (unsigned int i = 0; i < ARRAY_SIZE(bias_pins); i++) {
            bias_pins[i] = gpiod_get_index(&owner->dev, "bias", i, GPIOD_ASIS);
            if (IS_ERR(bias_pins[i])) {
                ret = PTR_ERR(bias_pins[i]); bias_pins[i] = NULL; goto out;
            }
            ret = gpiod_direction_output(bias_pins[i], 0);
            if (ret) goto out;
        }
        /* Same A523 tablet reference identifies PH18/19 as ENP/ENN. */
        gpiod_set_value_cansleep(bias_pins[0], 1); msleep(5);
        gpiod_set_value_cansleep(bias_pins[1], 1); msleep(40);
        pr_info("TZX DSI: candidate panel bias enable PH18 then PH19\n");
    }
    msleep(20);
    gpiod_set_value_cansleep(reset, 1);
    msleep(120);
    /* The base DT has no dsi1 mux function. All affected pins are claimed
     * above; use the vendor A523 PD10..19 function-4 mux, restoring it below. */
    for (unsigned int pin = 10; pin <= 19; pin++) {
        unsigned int off = 0x90 + (pin / 8) * 4, shift = (pin % 8) * 4;
        writel((readl(pio + off) & ~(15U << shift)) | (4U << shift), pio + off);
    }
    writel(0, host + 0x04); /* poll only, no interrupts */
    writel(0, host + 0x0c);
    writel(BIT(16) | BIT(17), host + 0x10);
    writel(0, host + 0x14); /* command mode */
    writel(0x1f, host + 0x20);        /* LP11 */
    writel(0x10000001, host + 0x24); /* BTA on lane 0 */
    writel(0x30100001, host + 0x30); /* LP command escape on lane 0 */
    writel(0x5000001f, host + 0x3c); /* delay in stop state */
    writel(2 | (3U << 28), host + 0x40);
    writel(49, host + 0x44);
    writel(49, host + 0x54);
    writel(0, host + 0x4c); writel(0, host + 0x50);
    writel(10, host + 0x60); writel(0, host + 0x78);
    writel(1, host + 0x00);
    msleep(20);
    {
        const u8 commands[] = {0x04, 0xda, 0xdb, 0xdc, 0x0a};
        for (unsigned int i = 0; i < ARRAY_SIZE(commands); i++)
            read_id(host, commands[i]);
    }
    if (wake_panel || dump_regs) {
        if (read_id(host, 0xda) != 0x93 || read_id(host, 0xdb) != 0x65 ||
            read_id(host, 0xdc) != 0x04) { ret = -ENODEV; goto out; }
    }
    if (dump_regs || wake_panel) {
        const u16 unlock[] = {0x00e0, 0x93e1, 0x65e2, 0xf8e3};
        for (unsigned int i = 0; i < ARRAY_SIZE(unlock); i++) {
            ret = lp_packet(host, 0x15, unlock[i], false);
            if (ret) goto out;
        }
    }
    if (dump_regs) {
        const u8 addresses[] = {0x00, 0x01, 0x03, 0x04, 0x17, 0x18, 0x24,
                                0x37, 0x3f, 0x55, 0x56, 0x57, 0x58};
        ret = lp_packet(host, 0x15, 0x01e0, false);
        if (ret) goto out;
        pr_info("TZX DSI: reading reset defaults on vendor page 1\n");
        for (unsigned int i = 0; i < ARRAY_SIZE(addresses); i++)
            read_id(host, addresses[i]);
        ret = lp_packet(host, 0x15, 0x00e0, false);
        if (ret) goto out;
    }
    if (wake_panel) {
        ret = lp_packet(host, 0x15, 0x773a, false); /* RGB888 */
        if (ret) goto out;
        ret = lp_packet(host, 0x05, 0x11, false); /* sleep out */
        if (ret) goto out;
        msleep(150);
        if (all_pixels_test) {
            ret = lp_packet(host, 0x05, 0x23, false);
            if (ret) goto out;
            msleep(20);
        }
        ret = lp_packet(host, 0x05, 0x29, false); /* display on */
        if (ret) goto out;
        msleep(150);
        pr_info("TZX DSI: standard wake completed, reading display status\n");
        for (unsigned int cmd = 0x0a; cmd <= 0x0f; cmd++) read_id(host, cmd);
    }
    if (video) {
        ret = prepare_video();
        if (ret) goto out;
        /* Return all-pixels-on test override to normal pixel data. */
        ret = lp_packet(host, 0x05, 0x13, false);
        if (ret) goto out;
        /* DCS reads use DLY with the clock lane enabled in LP stop state.
         * Start the continuous HS clock only after all LP transactions. */
        ret = start_hs_clock();
        if (ret) goto out;
        start_video();
    } else if (hs_clock) {
        ret = start_hs_clock();
        if (ret) goto out;
    }
    if (backlight || pwm_backlight) {
        bl = gpiod_get(&owner->dev, "backlight", GPIOD_ASIS);
        if (IS_ERR(bl)) { ret = PTR_ERR(bl); bl = NULL; goto out; }
        ret = gpiod_direction_output(bl, backlight ? 1 : 0);
        if (ret) goto out;
        if (pwm_backlight) {
            ret = enable_pwm_backlight();
            if (ret) goto out;
        } else pr_info("TZX DSI: candidate backlight PD23 high\n");
    }
    if (hold) {
        pr_info("TZX DSI: holding test state until module unload\n");
        return 0;
    }
out:
    release_probe();
    pr_info("TZX DSI: diagnostic finished ret=%d; resources restored\n", ret);
    return ret;
}

static void release_probe(void)
{
    if (!owner) return;
    release_video();
    if (pwm_saved) {
        writel(0, pwm + 0x80);
        for (unsigned int i = 0; i < ARRAY_SIZE(pwm_offsets); i++)
            writel(saved_pwm[i], pwm + pwm_offsets[i]);
    }
    if (pwm_reset_changed)
        writel((readl(ccu + 0x7ac) & ~BIT(16)) | (pwm_reset_saved & BIT(16)), ccu + 0x7ac);
    if (pwm_enabled) clk_disable_unprepare(pwm_clock);
    if (pwm_clock) clk_put(pwm_clock);
    if (pwm) iounmap(pwm);
    if (pwm_region) release_mem_region(0x02000c00, 0x400);
    if (bl) { gpiod_set_value_cansleep(bl, 0); gpiod_put(bl); }
    if (saved) {
        writel(0, host + 0x10); writel(0, host + 0x00);
        sun55i_dphy_pll_disable(&dphy);
        sun55i_dphy_analog_off(&dphy);
        for (unsigned int i = 0; i < ARRAY_SIZE(host_offsets); i++)
            writel(saved_host[i], host + host_offsets[i]);
        for (unsigned int i = 0; i < ARRAY_SIZE(phy_offsets); i++)
            writel(saved_phy[i], phy + phy_offsets[i]);
    }
    if (reset) { gpiod_set_value_cansleep(reset, 0); gpiod_put(reset); }
    for (unsigned int i = ARRAY_SIZE(bias_pins); i; i--) {
        if (bias_pins[i - 1]) {
            gpiod_set_value_cansleep(bias_pins[i - 1], 0);
            gpiod_put(bias_pins[i - 1]); msleep(5);
        }
    }
    if (bias_saved) {
        const u32 mask = BIT(18) | BIT(19);
        writel((readl(pio + 0x160) & ~mask) | (saved_ph_data & mask), pio + 0x160);
        writel((readl(pio + 0x158) & ~0xff00U) | (saved_ph_cfg & 0xff00U), pio + 0x158);
    }
    for (unsigned int i = 0; i < ARRAY_SIZE(lanes); i++)
        if (lanes[i]) gpiod_put(lanes[i]);
    if (lookup) gpiod_remove_lookup_table(&pins);
    if (pins_saved) {
        /* Only our reset data bit and lane/reset mux fields are restored. */
        u32 mask = BIT(22) | (bl ? BIT(23) : 0);
        writel((readl(pio + 0xa0) & ~mask) | (pd_data_saved & mask), pio + 0xa0);
        writel((readl(pio + 0x94) & 0xff) | (saved_pd[1] & ~0xffU), pio + 0x94);
        mask = 0x0f00ffffU | (bl ? 0xf0000000U : 0);
        writel((readl(pio + 0x98) & ~mask) | (saved_pd[2] & mask), pio + 0x98);
    }
    if (reset_changed)
        writel((readl(ccu + 0xb4c) & ~BIT(17)) | (reset_saved & BIT(17)), ccu + 0xb4c);
    while (enabled) clk_disable_unprepare(clocks[--enabled]);
    if (mod_rate) clk_set_rate(clocks[1], mod_rate);
    for (unsigned int i = 0; i < ARRAY_SIZE(clocks); i++) if (clocks[i]) clk_put(clocks[i]);
    if (pio) iounmap(pio);
    if (ccu) iounmap(ccu);
    if (phy) iounmap(phy);
    if (host) iounmap(host);
    if (phy_region) release_mem_region(0x05509000, 0x1000);
    if (host_region) release_mem_region(0x05508000, 0x1000);
    platform_device_unregister(owner);
    owner = NULL;
}
#ifdef TZX_PANEL_COMPONENT
#include <linux/backlight.h>
int __init tzx_panel_init(void);
void tzx_panel_exit(void);
void tzx_panel_blank(bool blank);
static struct backlight_device *panel_backlight;
static int panel_brightness(struct backlight_device *device)
{
    unsigned int brightness = backlight_get_brightness(device);
    writel((479U << 16) | (brightness * 480 / 100), pwm + 0x104);
    writel(brightness ? 1 : 0, pwm + 0x80);
    return 0;
}
static const struct backlight_ops panel_backlight_ops = {
    .options = BL_CORE_SUSPENDRESUME, .update_status = panel_brightness,
};
void tzx_panel_blank(bool blank)
{
    if (!panel_backlight) return;
    if (blank) backlight_disable(panel_backlight);
    else backlight_enable(panel_backlight);
}
int __init tzx_panel_init(void)
{
    struct backlight_properties properties = {
        .type = BACKLIGHT_RAW, .max_brightness = 100, .brightness = 20,
    };
    int ret;
    probe_panel = true; wake_panel = true; hold = true; video = true;
    bias = true; pwm_backlight = true; duty = 20; hs_clock = true;
    bsp_analog = true; bsp_pll = true; bsp_tcon = true;
    htotal = 880; hbp = 40; hsync = 20;
    vtotal = 1303; vbp = 11; vsync = 4; test_pattern = 1;
    ret = tzx_dsi_init();
    if (ret) return ret;
    panel_backlight = backlight_device_register("tzx-panel", &owner->dev,
                                               NULL, &panel_backlight_ops, &properties);
    if (IS_ERR(panel_backlight)) {
        ret = PTR_ERR(panel_backlight); panel_backlight = NULL;
        release_probe(); return ret;
    }
    return 0;
}
void tzx_panel_exit(void)
{
    if (panel_backlight) { backlight_device_unregister(panel_backlight); panel_backlight = NULL; }
    release_probe();
}
#else
static void __exit tzx_dsi_exit(void) { release_probe(); }
module_init(tzx_dsi_init);
module_exit(tzx_dsi_exit);
#endif
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX A523 reversible DSI1 PHY and LP read diagnostic");
