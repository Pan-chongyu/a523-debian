// SPDX-License-Identifier: GPL-2.0
/* Runtime-PM consumers keep the live display's domains accounted for. */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>

extern const char tzx_power_overlay[], tzx_power_overlay_end[];
static int overlay_id;

static void release_power(void *data)
{
    pm_runtime_put_sync(data);
    pm_runtime_disable(data);
}
static int power_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    int ret;
    pm_runtime_enable(dev);
    ret = pm_runtime_resume_and_get(dev);
    if (ret < 0) {
        pm_runtime_disable(dev);
        return ret;
    }
    return devm_add_action_or_reset(dev, release_power, dev);
}
static const struct of_device_id matches[] = {
    { .compatible = "tzx,p30-display-power" }, {}
};
MODULE_DEVICE_TABLE(of, matches);
static struct platform_driver power_driver = {
    .probe = power_probe,
    .driver = {
        .name = "tzx-display-power",
        .of_match_table = matches,
        .probe_type = PROBE_FORCE_SYNCHRONOUS,
    },
};
static int __init start(void)
{
    struct device_node *node, *provider;
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523"))
        return -ENODEV;
    node = of_find_node_by_path("/soc/power-controller@7060000");
    provider = of_find_node_by_phandle(TZX_PCK_PHANDLE);
    ret = node && node == provider ? 0 : -ENODEV;
    of_node_put(node);
    of_node_put(provider);
    if (ret)
        return ret;
    ret = platform_driver_register(&power_driver);
    if (ret)
        return ret;
    ret = of_overlay_fdt_apply(tzx_power_overlay,
                              tzx_power_overlay_end - tzx_power_overlay,
                              &overlay_id, NULL);
    if (ret)
        platform_driver_unregister(&power_driver);
    return ret;
}
static void __exit stop(void)
{
    of_overlay_remove(&overlay_id);
    platform_driver_unregister(&power_driver);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 display runtime-PM consumers for PCK600");
