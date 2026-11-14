// SPDX-License-Identifier: GPL-2.0
#include <linux/module.h>
#include <linux/of.h>
extern const char tzx_gpu_overlay[], tzx_gpu_overlay_end[];
static int overlay_id;
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
    return of_overlay_fdt_apply(tzx_gpu_overlay, tzx_gpu_overlay_end - tzx_gpu_overlay,
                                &overlay_id, NULL);
}
static void __exit stop(void)
{
    of_overlay_remove(&overlay_id);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 GPU node at fixed 200 MHz without regulator writes");
