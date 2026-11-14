// SPDX-License-Identifier: GPL-2.0-only
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>

extern const char tzx_gpu_devfreq_overlay[], tzx_gpu_devfreq_overlay_end[];
static int overlay_id;

static int __init start(void)
{
    struct i2c_adapter *adapter;
    struct device_node *node;
    struct platform_device *device;
    u8 address=0x84, value=0;
    struct i2c_msg msg[] = {
        {.addr=0x34,.len=1,.buf=&address},
        {.addr=0x34,.flags=I2C_M_RD,.len=1,.buf=&value},
    };
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523")) return -ENODEV;
    node=of_find_node_by_path("/soc/gpu@1800000");
    if (!node) return -ENODEV;
    device=of_find_device_by_node(node);
    of_node_put(node);
    if (device) {
        bool bound=device->dev.driver!=NULL;
        put_device(&device->dev);
        if (bound) return -EBUSY;
    }
    adapter=i2c_get_adapter(0);
    if (!adapter) return -ENODEV;
    ret=i2c_transfer(adapter,msg,2);
    i2c_put_adapter(adapter);
    if (ret!=2 || value!=0xa8) return -EPERM;
    return of_overlay_fdt_apply(tzx_gpu_devfreq_overlay,
        tzx_gpu_devfreq_overlay_end-tzx_gpu_devfreq_overlay,&overlay_id,NULL);
}
static void __exit stop(void)
{
    of_overlay_remove(&overlay_id);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX A523 native GPU OPPs on the existing unchanged 900mV rail");
