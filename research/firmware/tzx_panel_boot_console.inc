/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Claim the exact live SRAM panel without reset, bias cycling or PWM blanking.
 * This optional path is requested only after the userspace receipt/rail guard.
 * Cold initialization and its black-until-first-frame fallback stay available.
 */
static bool boot_console_adopt, panel_boot_adopted;
module_param(boot_console_adopt, bool, 0444);
module_param(panel_boot_adopted, bool, 0444);
bool tzx_panel_boot_active(void);

bool tzx_panel_boot_active(void)
{
    return panel_boot_adopted;
}

static int boot_clock_get(struct clk **array, unsigned int count,
                          const unsigned int *ids, unsigned int *enabled_count)
{
    struct device_node *node = of_find_node_by_path("/soc/clock-controller@2001000");
    int ret;
    if (!node) return -ENODEV;
    for (unsigned int i = 0; i < count; i++) {
        struct of_phandle_args spec = {.np = node, .args_count = 1, .args = {ids[i]}};
        array[i] = of_clk_get_from_provider(&spec);
        if (IS_ERR(array[i])) {
            ret = PTR_ERR(array[i]); array[i] = NULL; of_node_put(node); return ret;
        }
    }
    of_node_put(node);
    for (; *enabled_count < count; (*enabled_count)++) {
        ret = clk_prepare_enable(array[*enabled_count]);
        if (ret) return ret;
    }
    return 0;
}

static int boot_pin_get(struct gpio_desc **desc, const char *name, int index,
                        unsigned int pin)
{
    unsigned int bank = pin / 32, local = pin % 32;
    unsigned int offset = bank * 0x30 + local / 8 * 4;
    u32 saved_mux = readl(pio + offset), shift = local % 8 * 4;
    int ret;
    *desc = index < 0 ? gpiod_get(&owner->dev, name, GPIOD_ASIS) :
                       gpiod_get_index(&owner->dev, name, index, GPIOD_ASIS);
    ret = IS_ERR(*desc) ? PTR_ERR(*desc) : 0;
    if (ret) *desc = NULL;
    /* gpio_request_enable may select GPIO; restore only this claimed mux. */
    writel((readl(pio + offset) & ~(15U << shift)) | (saved_mux & (15U << shift)),
           pio + offset);
    return ret;
}

static int adopt_live_panel(void)
{
    const unsigned int dsi_ids[] = {CLK_BUS_MIPI_DSI1, CLK_MIPI_DSI1, CLK_COMBOPHY_DSI1};
    const unsigned int video_ids[] = {CLK_BUS_DISPLAY0_TOP, CLK_BUS_TCON_LCD1, CLK_TCON_LCD1};
    const unsigned int pwm_ids[] = {CLK_BUS_PWM0};
    void __iomem *receipt;
    int ret;
    u32 before, after;

    receipt = ioremap(0x2d000, 4096);
    if (!receipt) return -ENOMEM;
    ret = readl(receipt + 0x200) == 0xa523ed01 && readl(receipt + 0x20c) == 1 &&
          readl(receipt + 0x600) == 0xa523b001 && readl(receipt + 0x60c) == 1 &&
          !readl(receipt + 0x610) && readl(receipt + 0x620 + 3 * 8 + 7 * 4) == 0x42400000;
    /* The stable receipt field is independently checked below in live DE. */
    iounmap(receipt);
    if (!ret) { pr_err("TZX PANEL: boot adoption receipt rejected\n"); return -EINVAL; }
    if (!request_mem_region(0x05502000, 4096, "tzx-boot-tcon")) return -EBUSY;
    tcon_region = true;
    if (!request_mem_region(0x05500000, 4096, "tzx-boot-top")) return -EBUSY;
    top_region = true;
    if (!request_mem_region(0x02000c00, 0x400, "tzx-boot-pwm")) return -EBUSY;
    pwm_region = true;
    tcon = ioremap(0x05502000, 4096);
    display_top = ioremap(0x05500000, 4096);
    pwm = ioremap(0x02000c00, 0x400);
    if (!tcon || !display_top || !pwm) return -ENOMEM;
    /* Linux's power-domain consumer may have gated the buses. Take CCF
     * references before MMIO validation; a gated bus reads as all zero. */
    ret = boot_clock_get(clocks, ARRAY_SIZE(clocks), dsi_ids, &enabled);
    if (ret) return ret;
    ret = boot_clock_get(video_clocks, ARRAY_SIZE(video_clocks), video_ids, &video_enabled);
    if (ret) return ret;
    { unsigned int on = 0;
      ret = boot_clock_get(&pwm_clock, 1, pwm_ids, &on); pwm_enabled = on != 0; }
    if (ret) return ret;
    pr_info("TZX PANEL: live ownership CCU dsi=%08x tcon=%08x top=%08x clocks=%08x/%08x\n",
        readl(ccu + 0xb4c), readl(ccu + 0xb7c), readl(ccu + 0xabc),
        readl(ccu + 0xb64), readl(ccu + 0xb70));
    /* These writes only release reset; never assert a running block's reset. */
    writel(readl(ccu + 0xb4c) | BIT(17), ccu + 0xb4c);
    writel(readl(ccu + 0xb7c) | BIT(17), ccu + 0xb7c);
    writel(readl(ccu + 0xabc) | BIT(16), ccu + 0xabc);
    usleep_range(100, 200);
    if ((readl(tcon + 0x40) & (BIT(31) | 7)) != BIT(31) ||
        readl(tcon + 0x48) != ((799U << 16) | 1279) ||
        readl(tcon + 0x4c) != ((879U << 16) | 39) ||
        readl(tcon + 0x50) != ((2606U << 16) | 10) ||
        readl(host + 0x2f8) != 0xff || !(readl(host + 0x10) & 1) ||
        !(readl(pwm + 0x80) & 1) || (readl(pwm + 0x104) >> 16) != 479 ||
        (readl(pio + 0x160) & (BIT(18) | BIT(19))) != (BIT(18) | BIT(19)) ||
        !(readl(pio + 0xa0) & BIT(22))) {
        pr_err("TZX PANEL: boot adoption registers ctl=%08x timing=%08x/%08x/%08x host=%08x/%08x PWM=%08x/%08x pins=%08x/%08x\n",
            readl(tcon + 0x40), readl(tcon + 0x48), readl(tcon + 0x4c), readl(tcon + 0x50),
            readl(host + 0x2f8), readl(host + 0x10), readl(pwm + 0x80), readl(pwm + 0x104),
            readl(pio + 0x160), readl(pio + 0xa0));
        return -EINVAL;
    }
    before = readl(host + 0x2e0); usleep_range(30000, 35000); after = readl(host + 0x2e0);
    if (before == after) return -ETIMEDOUT;

    /* Teardown returns to disabled hardware, never to an active SRAM owner. */
    reset_saved &= ~(BIT(17) | BIT(1)); reset_changed = true;
    tcon_reset_saved = readl(ccu + 0xb7c) & ~(BIT(17) | BIT(1));
    top_reset_saved = readl(ccu + 0xabc) & ~(BIT(16) | BIT(0));
    pwm_reset_saved = readl(ccu + 0x7ac) & ~(BIT(16) | BIT(0));
    video_reset_changed = pwm_reset_changed = true;
    memset(tcon_saved, 0, sizeof(tcon_saved)); tcon_saved[5] = 1;
    for (unsigned int i = 0; i < ARRAY_SIZE(top_offsets); i++)
        top_saved[i] = readl(display_top + top_offsets[i]);
    video_saved = true;
    for (unsigned int i = 0; i < ARRAY_SIZE(pwm_offsets); i++)
        saved_pwm[i] = readl(pwm + pwm_offsets[i]);
    saved_pwm[2] = 0; pwm_saved = true;
    for (unsigned int i = 0; i < 3; i++) saved_pd[i] = readl(pio + 0x90 + i * 4);
    pd_data_saved = readl(pio + 0xa0); pins_saved = true;
    saved_ph_cfg = readl(pio + 0x158); saved_ph_data = readl(pio + 0x160) & ~(BIT(18) | BIT(19));
    bias_saved = true;
    gpiod_add_lookup_table(&pins); lookup = true;
    for (unsigned int i = 0; i < ARRAY_SIZE(lanes); i++) {
        ret = boot_pin_get(&lanes[i], "lane", i, 106 + i); if (ret) return ret;
    }
    ret = boot_pin_get(&reset, "reset", -1, 118); if (ret) return ret;
    ret = boot_pin_get(&bl, "backlight", -1, 119); if (ret) return ret;
    for (unsigned int i = 0; i < ARRAY_SIZE(bias_pins); i++) {
        ret = boot_pin_get(&bias_pins[i], "bias", i, 242 + i); if (ret) return ret;
    }
    dphy.base = phy; dphy.hs_clk_rate = hs_rate;
    panel_boot_adopted = true; panel_frame_committed = true;
    panel_startup_black = false; panel_power_phase = 8; panel_power_status = 0x18;
    snprintf(report, sizeof(report), "adopted live SRAM panel; no reset/rail/PWM off; line=%08x/%08x", before, after);
    pr_info("TZX PANEL: %s\n", report);
    return 0;
}
