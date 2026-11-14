// SPDX-License-Identifier: GPL-2.0-only
/* Temporary open-drain ID-reading buses on documented, unclaimed TWI pins.
 * No reset, clock, rail or PMIC operations; preserve GPIO configuration.
 */
#include <linux/gpio/machine.h>
#include <linux/i2c.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_data/i2c-gpio.h>
#include <linux/platform_device.h>

static int candidate = 1;
module_param(candidate, int, 0444);
static struct platform_device *bus;
static void __iomem *pio;
static u32 cfg_offset, cfg_mask, data_offset, data_mask, old_cfg, old_data;
static bool saved, lookup_added;
static struct gpiod_lookup_table pins = {
	.dev_id = "i2c-gpio.17",
	.table = {
		GPIO_LOOKUP("2000000.pinctrl", 227, "sda", GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN),
		GPIO_LOOKUP("2000000.pinctrl", 226, "scl", GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN),
		{}
	}
};

static void stop(void)
{
	if (bus) {
		platform_device_unregister(bus);
		bus = NULL;
	}
	if (lookup_added)
		gpiod_remove_lookup_table(&pins);
	if (pio) {
		if (saved) {
			/* Return data latches before restoring the original input/disabled mux. */
			writel((readl(pio+data_offset) & ~data_mask) | (old_data & data_mask), pio+data_offset);
			writel((readl(pio+cfg_offset) & ~cfg_mask) | (old_cfg & cfg_mask), pio+cfg_offset);
		}
		iounmap(pio);
	}
}

static int __init start(void)
{
	struct i2c_gpio_platform_data timing = { .udelay = 10, .timeout = HZ/20 };
	struct i2c_adapter *adapter;
	int id, bank, first, ret, pin, function;

	if (!of_machine_is_compatible("tzx,p30a523") || (candidate != 1 && candidate != 3))
		return -ENODEV;
	if (candidate == 3) {
		pins.dev_id = "i2c-gpio.19";
		pins.table[0].chip_hwnum = 132;
		pins.table[1].chip_hwnum = 131;
	}
	id = 16+candidate;
	bank = candidate == 1 ? 7 : 4;
	first = candidate == 1 ? 2 : 3;
	adapter = i2c_get_adapter(id);
	if (adapter) {
		i2c_put_adapter(adapter);
		return -EBUSY;
	}
	pio = ioremap(0x02000000, 0x1000);
	if (!pio)
		return -ENOMEM;
	cfg_offset = bank*0x30;
	data_offset = cfg_offset+0x10;
	cfg_mask = 0xffU << (first*4);
	data_mask = 3U << first;
	old_cfg = readl(pio+cfg_offset);
	old_data = readl(pio+data_offset);
	/* A523 mux 0 is input and 15 is IO disabled (SUN4I_FUNC_DISABLED_NEW).
	 * Reject output, IRQ and every peripheral function. GPIO ownership is
	 * then claimed by i2c-gpio itself and conflicts are rejected there. */
	for (pin = first; pin < first+2; pin++) {
		function = (old_cfg >> (pin*4)) & 15;
		if (function != 0 && function != 15) {
			ret = -EBUSY;
			goto fail;
		}
	}
	saved = true;
	gpiod_add_lookup_table(&pins);
	lookup_added = true;
	bus = platform_device_register_data(NULL, "i2c-gpio", id, &timing, sizeof(timing));
	if (IS_ERR(bus)) {
		ret = PTR_ERR(bus);
		bus = NULL;
		goto fail;
	}
	adapter = i2c_get_adapter(id);
	if (!adapter) {
		ret = -ENODEV;
		goto fail;
	}
	ret = adapter->dev.parent == &bus->dev ? 0 : -EBUSY;
	i2c_put_adapter(adapter);
	if (ret)
		goto fail;
	pr_info("tzx-candidate-i2c: candidate TWI%d on bus%d, open drain; no power/reset changes\n", candidate, id);
	return 0;
fail:
	stop();
	return ret;
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 temporary unclaimed TWI1/TWI3 GPIO ID-reading buses");
