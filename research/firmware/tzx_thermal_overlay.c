// SPDX-License-Identifier: GPL-2.0
/* Dynamic thermal nodes for the exact frozen TZX P30 base DTB. */
#include <linux/clk-provider.h>
#include <linux/err.h>
#include <linux/module.h>
#include <linux/of.h>

extern const char tzx_thermal_overlay[], tzx_thermal_overlay_end[];
static int overlay_id;
static struct clk_hw *hosc_alias;

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

    /* The two mainline GPADC clocks use a global parent named "hosc";
     * this board's fixed clock is named "osc24M". Supply only the missing
     * name, without changing either oscillator or any clock register. */
    hosc_alias = clk_hw_register_fixed_factor(NULL, "hosc", "osc24M", 0, 1, 1);
    if (IS_ERR(hosc_alias))
        return PTR_ERR(hosc_alias);
    ret = of_overlay_fdt_apply(tzx_thermal_overlay,
                              tzx_thermal_overlay_end - tzx_thermal_overlay,
                              &overlay_id, NULL);
    if (ret)
        clk_hw_unregister_fixed_factor(hosc_alias);
    return ret;
}

static void __exit stop(void)
{
    of_overlay_remove(&overlay_id);
    clk_hw_unregister_fixed_factor(hosc_alias);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 thermal nodes and GPADC parent clock alias");
