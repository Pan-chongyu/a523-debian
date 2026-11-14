// SPDX-License-Identifier: GPL-2.0
#include <linux/module.h>
#include <linux/of.h>
extern const char tzx_video_overlay[], tzx_video_overlay_end[];
static int overlay_id;
static bool provider(const char *path,u32 handle)
{
    struct device_node *a=of_find_node_by_path(path),*b=of_find_node_by_phandle(handle);
    bool good=a && a==b;
    of_node_put(a);of_node_put(b);return good;
}
static int __init start(void)
{
    if(!of_machine_is_compatible("tzx,p30a523") ||
       !provider("/soc/interrupt-controller@3400000",1) ||
       !provider("/soc/clock-controller@2001000",2) ||
       !provider("/soc/power-controller@7060000",3) ||
       !provider("/soc/iommu@2010000",0x90)) return -ENODEV;
    return of_overlay_fdt_apply(tzx_video_overlay,tzx_video_overlay_end-tzx_video_overlay,&overlay_id,NULL);
}
static void __exit stop(void) {of_overlay_remove(&overlay_id);}
module_init(start);module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 VPU node; VE0/VE1 IOMMU; existing display bypass preserved");
