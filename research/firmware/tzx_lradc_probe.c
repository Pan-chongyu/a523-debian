// SPDX-License-Identifier: GPL-2.0
/* Bounded diagnostic: LRADC samples, no IRQ and no input event mapping. */
#include <linux/clk.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/reset.h>

extern const char tzx_lradc_overlay[], tzx_lradc_overlay_end[];
static int overlay_id;
struct probe_data {
    void __iomem *base;
    struct clk *clk;
    struct reset_control *reset;
    u32 control, interrupts;
    int was_reset;
};

static ssize_t raw_show(struct device *dev, struct device_attribute *attr, char *buf)
{
    struct probe_data *data = dev_get_drvdata(dev);
    return sysfs_emit(buf, "%08x %08x %08x %08x %08x\n",
        readl(data->base), readl(data->base+4), readl(data->base+8),
        readl(data->base+12), readl(data->base+16));
}
static DEVICE_ATTR_RO(raw);

static void restore(struct probe_data *data)
{
    writel(data->control, data->base);
    writel(data->interrupts, data->base+4);
    clk_disable_unprepare(data->clk);
    if (data->was_reset)
        reset_control_assert(data->reset);
}

static int probe(struct platform_device *pdev)
{
    struct probe_data *data;
    int ret;
    data = devm_kzalloc(&pdev->dev, sizeof(*data), GFP_KERNEL);
    if (!data)
        return -ENOMEM;
    data->base = devm_platform_ioremap_resource(pdev, 0);
    if (IS_ERR(data->base))
        return PTR_ERR(data->base);
    data->clk = devm_clk_get(&pdev->dev, NULL);
    if (IS_ERR(data->clk))
        return PTR_ERR(data->clk);
    data->reset = devm_reset_control_get_exclusive(&pdev->dev, NULL);
    if (IS_ERR(data->reset))
        return PTR_ERR(data->reset);
    data->was_reset = reset_control_status(data->reset);
    if (data->was_reset < 0)
        return data->was_reset;
    ret = reset_control_deassert(data->reset);
    if (ret)
        return ret;
    ret = clk_prepare_enable(data->clk);
    if (ret) {
        if (data->was_reset)
            reset_control_assert(data->reset);
        return ret;
    }
    data->control = readl(data->base);
    data->interrupts = readl(data->base+4);
    if (data->interrupts || data->control & 1) {
        restore(data);
        return -EBUSY;
    }
    platform_set_drvdata(pdev, data);
    /* 250 Hz, initial delay 8 ms, channel0 and A523 HOLD_KEY_EN.
     * No interrupt is enabled. Do not alter reference-supply voltage. */
    writel(0, data->base+4);
    writel((2U<<24) | BIT(8) | BIT(7) | BIT(6) | BIT(0), data->base);
    ret = device_create_file(&pdev->dev, &dev_attr_raw);
    if (ret)
        restore(data);
    return ret;
}

static void remove_probe(struct platform_device *pdev)
{
    device_remove_file(&pdev->dev, &dev_attr_raw);
    restore(platform_get_drvdata(pdev));
}

static const struct of_device_id match[] = {
    { .compatible = "tzx,p30-lradc-probe" }, { }
};
static struct platform_driver driver = {
    .probe = probe, .remove = remove_probe,
    .driver = { .name = "tzx-lradc-probe", .of_match_table = match }
};

static int __init start(void)
{
    struct device_node *node, *provider;
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523"))
        return -ENODEV;
    node = of_find_node_by_path("/soc/clock-controller@2001000");
    provider = of_find_node_by_phandle(2);
    ret = node && node == provider ? 0 : -ENODEV;
    of_node_put(node);
    of_node_put(provider);
    if (ret)
        return ret;
    ret = platform_driver_register(&driver);
    if (ret)
        return ret;
    ret = of_overlay_fdt_apply(tzx_lradc_overlay,
        tzx_lradc_overlay_end-tzx_lradc_overlay, &overlay_id, NULL);
    if (ret)
        platform_driver_unregister(&driver);
    return ret;
}
static void __exit stop(void)
{
    of_overlay_remove(&overlay_id);
    platform_driver_unregister(&driver);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 reversible LRADC raw diagnostic");
