// SPDX-License-Identifier: GPL-2.0-only
/* Register the verified PH0/PH1 touch bus after boot. This avoids changing
 * the boot DT during driver tests. All devices and GPIOs unwind on unload. */
#include <linux/module.h>
#include <linux/err.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio/machine.h>
#include <linux/i2c.h>
#include <linux/irq.h>
#include <linux/jiffies.h>
#include <linux/of.h>
#include <linux/platform_data/i2c-gpio.h>
#include <linux/platform_device.h>
#include <linux/property.h>

static struct platform_device *owner,*bus;
static struct gpio_desc *irq_gpio;
static struct i2c_client *touch;
static struct gpiod_lookup_table bus_gpios={
    .dev_id="i2c-gpio.1",
    .table={
        GPIO_LOOKUP("2000000.pinctrl",225,"sda",GPIO_ACTIVE_HIGH|GPIO_OPEN_DRAIN),
        GPIO_LOOKUP("2000000.pinctrl",224,"scl",GPIO_ACTIVE_HIGH|GPIO_OPEN_DRAIN),{}
    }
};
static struct gpiod_lookup_table power_gpio={
    .dev_id="1-0040",
    .table={GPIO_LOOKUP("2000000.pinctrl",234,"power",GPIO_ACTIVE_HIGH),{}}
};
static struct gpiod_lookup_table interrupt_gpio={
    .dev_id="tzx-touch-runtime",
    .table={GPIO_LOOKUP("2000000.pinctrl",233,"irq",GPIO_ACTIVE_HIGH),{}}
};
static const struct property_entry touch_properties[]={
    PROPERTY_ENTRY_STRING("firmware-name","silead/tzx-p30-candidate.fw"),
    PROPERTY_ENTRY_U32("touchscreen-size-x",1648),
    PROPERTY_ENTRY_U32("touchscreen-size-y",880),
    PROPERTY_ENTRY_BOOL("touchscreen-swapped-x-y"),
    PROPERTY_ENTRY_BOOL("touchscreen-inverted-y"),
    PROPERTY_ENTRY_BOOL("tzx,externally-powered"),{}
};
static const struct software_node touch_node={
    .name="tzx-gsl3670-runtime",.properties=touch_properties
};

static void release_devices(void)
{
    if(touch){i2c_unregister_device(touch);touch=NULL;}
    if(irq_gpio){gpiod_put(irq_gpio);irq_gpio=NULL;}
    if(bus){platform_device_unregister(bus);bus=NULL;}
    if(owner){platform_device_unregister(owner);owner=NULL;}
    gpiod_remove_lookup_table(&interrupt_gpio);
    gpiod_remove_lookup_table(&power_gpio);
    gpiod_remove_lookup_table(&bus_gpios);
}
static int __init tzx_runtime_init(void)
{
    struct i2c_adapter *adapter;
    struct i2c_gpio_platform_data timing={.udelay=10,.timeout=HZ/10};
    struct i2c_board_info info={I2C_BOARD_INFO("tzx-gsl3670",0x40),.swnode=&touch_node};
    int ret;
    if(!of_machine_is_compatible("tzx,p30a523"))return -ENODEV;
    adapter=i2c_get_adapter(1);
    if(adapter){i2c_put_adapter(adapter);return -EBUSY;}
    gpiod_add_lookup_table(&bus_gpios);
    gpiod_add_lookup_table(&power_gpio);
    gpiod_add_lookup_table(&interrupt_gpio);
    owner=platform_device_register_simple("tzx-touch-runtime",PLATFORM_DEVID_NONE,NULL,0);
    if(IS_ERR(owner)){ret=PTR_ERR(owner);owner=NULL;goto fail;}
    irq_gpio=gpiod_get(&owner->dev,"irq",GPIOD_IN);
    if(IS_ERR(irq_gpio)){ret=PTR_ERR(irq_gpio);irq_gpio=NULL;goto fail;}
    info.irq=gpiod_to_irq(irq_gpio);
    if(info.irq<0){ret=info.irq;goto fail;}
    ret=irq_set_irq_type(info.irq,IRQ_TYPE_EDGE_RISING);
    if(ret)goto fail;
    bus=platform_device_register_data(NULL,"i2c-gpio",1,&timing,sizeof(timing));
    if(IS_ERR(bus)){ret=PTR_ERR(bus);bus=NULL;goto fail;}
    adapter=i2c_get_adapter(1);
    if(!adapter){ret=-ENODEV;goto fail;}
    if(adapter->dev.parent!=&bus->dev){ret=-EBUSY;i2c_put_adapter(adapter);goto fail;}
    touch=i2c_new_client_device(adapter,&info);
    i2c_put_adapter(adapter);
    if(IS_ERR(touch)){ret=PTR_ERR(touch);touch=NULL;goto fail;}
    pr_info("TZX runtime touch: bus PH0/PH1, reset PH10, candidate IRQ PH9=%d\n",info.irq);
    return 0;
fail:
    release_devices();return ret;
}
module_init(tzx_runtime_init);
module_exit(release_devices);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Reversible TZX P30 runtime touch bus registration");
