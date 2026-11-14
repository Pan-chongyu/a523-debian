// SPDX-License-Identifier: GPL-2.0
/* AXP717 PEK bridge until the board can use the complete PMIC MFD. */
#include <linux/i2c.h>
#include <linux/input.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

static struct i2c_adapter *adapter;
static struct platform_device *parent;
static struct input_dev *input;
static bool pressed;

static int read_edges(void)
{
    u8 reg = 0x49, value;
    struct i2c_msg msg[] = {
        { .addr = 0x34, .len = 1, .buf = &reg },
        { .addr = 0x34, .flags = I2C_M_RD, .len = 1, .buf = &value }
    };
    struct device *owner;
    int ret;
    owner = bus_find_device_by_name(&i2c_bus_type, NULL, "0-0034");
    if (owner) {
        put_device(owner);
        return -EBUSY;
    }
    ret = i2c_transfer(adapter, msg, ARRAY_SIZE(msg));
    return ret == ARRAY_SIZE(msg) ? value & 3 : (ret < 0 ? ret : -EIO);
}

static int ack_edges(u8 value)
{
    u8 bytes[] = { 0x49, value & 3 };
    struct i2c_msg msg = { .addr = 0x34, .len = 2, .buf = bytes };
    int ret = i2c_transfer(adapter, &msg, 1);
    return ret == 1 ? 0 : (ret < 0 ? ret : -EIO);
}

static void poll_key(struct input_dev *dev)
{
    int edges = read_edges();
    if (edges < 0) {
        if (pressed) {
            input_report_key(dev, KEY_POWER, 0);
            input_sync(dev);
            pressed = false;
        }
        return;
    }
    if (!edges || ack_edges(edges))
        return;
    /* Falling bit1 = pressed, rising bit0 = released. If both accumulate,
     * report a complete tap; never leave a power key stuck down. */
    if ((edges & 2) && !pressed) {
        input_report_key(dev, KEY_POWER, 1);
        input_sync(dev);
        pressed = true;
    }
    if ((edges & 1) && pressed) {
        input_report_key(dev, KEY_POWER, 0);
        input_sync(dev);
        pressed = false;
    }
}

static int __init start(void)
{
    int ret, edges;
    if (!of_machine_is_compatible("tzx,p30a523"))
        return -ENODEV;
    adapter = i2c_get_adapter(0);
    if (!adapter)
        return -ENODEV;
    edges = read_edges();
    if (edges < 0) {
        ret = edges;
        goto put;
    }
    if (edges) {
        ret = ack_edges(edges);
        if (ret)
            goto put;
    }
    parent = platform_device_register_simple("tzx-axp717-power-key", -1, NULL, 0);
    if (IS_ERR(parent)) {
        ret = PTR_ERR(parent);
        goto put;
    }
    input = input_allocate_device();
    if (!input) {
        ret = -ENOMEM;
        goto unregister;
    }
    input->name = "TZX P30 AXP717 power key";
    input->phys = "tzx-axp717/input0";
    input->id.bustype = BUS_I2C;
    input->dev.parent = &parent->dev;
    input_set_capability(input, EV_KEY, KEY_POWER);
    ret = input_setup_polling(input, poll_key);
    if (!ret) {
        input_set_poll_interval(input, 20);
        ret = input_register_device(input);
    }
    if (!ret)
        return 0;
    input_free_device(input);
unregister:
    platform_device_unregister(parent);
put:
    i2c_put_adapter(adapter);
    return ret;
}

static void __exit stop(void)
{
    input_unregister_device(input);
    platform_device_unregister(parent);
    i2c_put_adapter(adapter);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 AXP717 PEK input bridge, no charger or rail writes");
