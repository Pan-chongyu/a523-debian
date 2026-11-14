// SPDX-License-Identifier: GPL-2.0-only
/* Read-only AXP717 telemetry for this board's transitional PMIC setup.
 * Register definitions and scaling follow Linux axp20x_battery/axp20x_adc.
 * This module deliberately has no charger, ADC-enable or fault-clear writes.
 */
#include <linux/module.h>
#include <linux/i2c.h>
#include <linux/mfd/axp20x.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/workqueue.h>

struct tzx_sample {
	bool valid, voltage_valid;
	u8 power, status, percent;
	int voltage_uv;
};

static struct i2c_adapter *adapter;
static struct platform_device *parent;
static struct power_supply *battery, *usb;
static DEFINE_MUTEX(sample_lock);
static struct tzx_sample sample;
static struct delayed_work poll_work;

static int pmic_read(u8 reg, void *data, size_t len)
{
	struct i2c_msg messages[] = {
		{ .addr = 0x34, .len = 1, .buf = &reg },
		{ .addr = 0x34, .flags = I2C_M_RD, .len = len, .buf = data },
	};
	int ret;
	struct device *owner;

	/* Yield to a future proper MFD driver if it takes ownership. */
	owner = bus_find_device_by_name(&i2c_bus_type, NULL, "0-0034");
	if (owner) {
		put_device(owner);
		return -EBUSY;
	}
	ret = i2c_transfer(adapter, messages, ARRAY_SIZE(messages));
	return ret == ARRAY_SIZE(messages) ? 0 : (ret < 0 ? ret : -EIO);
}

static int take_sample(struct tzx_sample *next)
{
	u8 adc, volts[2];
	int ret;

	memset(next, 0, sizeof(*next));
	ret = pmic_read(AXP717_ON_INDICATE, &next->power, 1);
	if (ret)
		return ret;
	ret = pmic_read(AXP717_PMU_STATUS_2, &next->status, 1);
	if (ret)
		return ret;
	ret = pmic_read(AXP717_BATT_PERCENT_DATA, &next->percent, 1);
	if (ret)
		return ret;
	next->percent &= 0x7f;
	ret = pmic_read(AXP717_ADC_CH_EN_CONTROL, &adc, 1);
	if (ret)
		return ret;
	if (adc & BIT(0)) {
		ret = pmic_read(AXP717_BATT_V_H, volts, 2);
		if (ret)
			return ret;
		next->voltage_uv = (((volts[0] << 8) | volts[1]) & 0x3fff) * 1000;
		next->voltage_valid = true;
	}
	next->valid = true;
	return 0;
}

static int battery_get(struct power_supply *psy,
		       enum power_supply_property prop,
		       union power_supply_propval *value)
{
	struct tzx_sample now;

	mutex_lock(&sample_lock);
	now = sample;
	mutex_unlock(&sample_lock);
	if (!now.valid)
		return -ENODATA;
	switch (prop) {
	case POWER_SUPPLY_PROP_PRESENT:
		value->intval = !!(now.power & BIT(3));
		return 0;
	case POWER_SUPPLY_PROP_STATUS:
		switch ((now.status >> 5) & 3) {
		case 0: value->intval = POWER_SUPPLY_STATUS_NOT_CHARGING; break;
		case 1: value->intval = POWER_SUPPLY_STATUS_CHARGING; break;
		case 2: value->intval = POWER_SUPPLY_STATUS_DISCHARGING; break;
		default: value->intval = POWER_SUPPLY_STATUS_UNKNOWN; break;
		}
		return 0;
	case POWER_SUPPLY_PROP_CAPACITY:
		if (!(now.power & BIT(3)) || now.percent > 100)
			return -ENODATA;
		value->intval = now.percent;
		return 0;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		if (!(now.power & BIT(3)) || !now.voltage_valid)
			return -ENODATA;
		value->intval = now.voltage_uv;
		return 0;
	default:
		return -EINVAL;
	}
}

static int usb_get(struct power_supply *psy, enum power_supply_property prop,
		   union power_supply_propval *value)
{
	struct tzx_sample now;

	if (prop != POWER_SUPPLY_PROP_ONLINE)
		return -EINVAL;
	mutex_lock(&sample_lock);
	now = sample;
	mutex_unlock(&sample_lock);
	if (!now.valid)
		return -ENODATA;
	value->intval = !!(now.power & BIT(5));
	return 0;
}

static enum power_supply_property battery_props[] = {
	POWER_SUPPLY_PROP_PRESENT, POWER_SUPPLY_PROP_STATUS,
	POWER_SUPPLY_PROP_CAPACITY, POWER_SUPPLY_PROP_VOLTAGE_NOW,
};
static enum power_supply_property usb_props[] = { POWER_SUPPLY_PROP_ONLINE };
static const struct power_supply_desc battery_desc = {
	.name = "tzx-battery", .type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = battery_props, .num_properties = ARRAY_SIZE(battery_props),
	.get_property = battery_get,
};
static const struct power_supply_desc usb_desc = {
	.name = "tzx-usb", .type = POWER_SUPPLY_TYPE_USB,
	.properties = usb_props, .num_properties = ARRAY_SIZE(usb_props),
	.get_property = usb_get,
};

static void poll(struct work_struct *work)
{
	struct tzx_sample next;
	bool changed;

	if (take_sample(&next))
		next.valid = false;
	mutex_lock(&sample_lock);
	changed = memcmp(&next, &sample, sizeof(next));
	sample = next;
	mutex_unlock(&sample_lock);
	if (changed) {
		power_supply_changed(battery);
		power_supply_changed(usb);
	}
	schedule_delayed_work(&poll_work, 10 * HZ);
}

static int __init tzx_battery_init(void)
{
	struct power_supply_config config = { .no_wakeup_source = true };
	int ret;

	if (!of_machine_is_compatible("tzx,p30a523"))
		return -ENODEV;
	adapter = i2c_get_adapter(0);
	if (!adapter)
		return -ENODEV;
	ret = take_sample(&sample);
	if (ret)
		goto put_adapter;
	parent = platform_device_register_simple("tzx-battery", -1, NULL, 0);
	if (IS_ERR(parent)) {
		ret = PTR_ERR(parent);
		goto put_adapter;
	}
	battery = power_supply_register(&parent->dev, &battery_desc, &config);
	if (IS_ERR(battery)) {
		ret = PTR_ERR(battery);
		goto remove_parent;
	}
	usb = power_supply_register(&parent->dev, &usb_desc, &config);
	if (IS_ERR(usb)) {
		ret = PTR_ERR(usb);
		goto remove_battery;
	}
	INIT_DELAYED_WORK(&poll_work, poll);
	schedule_delayed_work(&poll_work, 10 * HZ);
	pr_info("tzx-battery: read-only AXP717 telemetry, %u%% %duV VBUS=%u\n",
		sample.percent, sample.voltage_uv, !!(sample.power & BIT(5)));
	return 0;

remove_battery:
	power_supply_unregister(battery);
remove_parent:
	platform_device_unregister(parent);
put_adapter:
	i2c_put_adapter(adapter);
	return ret;
}

static void __exit tzx_battery_exit(void)
{
	cancel_delayed_work_sync(&poll_work);
	power_supply_unregister(usb);
	power_supply_unregister(battery);
	platform_device_unregister(parent);
	i2c_put_adapter(adapter);
}
module_init(tzx_battery_init);
module_exit(tzx_battery_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 AXP717 read-only battery and USB telemetry");
