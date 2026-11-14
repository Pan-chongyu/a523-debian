// SPDX-License-Identifier: GPL-2.0-only
/* Transitional AXP717 soft power-off for the exact TZX P30 board.
 * I2C may sleep: use POWER_OFF_PREPARE, after device shutdown, before the
 * atomic PSCI power-off. No writes on module load/unload or on reboot.
 */
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/reboot.h>

static struct i2c_adapter *adapter;
static struct sys_off_handler *handler;
static bool armed;
module_param(armed, bool, 0444);
MODULE_PARM_DESC(armed, "Allow REG27 bit0 only during normal kernel power-off");

static int read_reg(u16 addr, u8 reg)
{
	u8 value;
	struct i2c_msg msgs[] = {
		{ .addr = addr, .len = 1, .buf = &reg },
		{ .addr = addr, .flags = I2C_M_RD, .len = 1, .buf = &value },
	};
	int ret = i2c_transfer(adapter, msgs, ARRAY_SIZE(msgs));

	return ret == ARRAY_SIZE(msgs) ? value : (ret < 0 ? ret : -EIO);
}

static int board_pmic_guard(void)
{
	static const u8 registers[][2] = {
		{ 0x80, 0x0f }, { 0x83, 0xa8 }, { 0x84, 0xa8 }, { 0x85, 0xc9 },
	};
	struct device *owner;
	unsigned int i;
	int value;

	/* Do not coexist with a future proper MFD owner. */
	owner = bus_find_device_by_name(&i2c_bus_type, NULL, "0-0034");
	if (owner) {
		put_device(owner);
		return -EBUSY;
	}
	value = read_reg(0x36, 0x03);
	if (value != 0x49)
		return value < 0 ? value : -ENODEV;
	for (i = 0; i < ARRAY_SIZE(registers); i++) {
		value = read_reg(0x34, registers[i][0]);
		if (value != registers[i][1])
			return value < 0 ? value : -ENODEV;
	}
	value = read_reg(0x34, 0x27);
	if (value < 0)
		return value;
	/* Reject active restart/off requests or unknown reserved bits. */
	return value & 0xf3 ? -EINVAL : value;
}

static int poweroff_prepare(struct sys_off_data *data)
{
	u8 bytes[2];
	struct i2c_msg msg = { .addr = 0x34, .len = 2, .buf = bytes };
	int control, ret;

	if (!armed) {
		pr_notice("tzx-poweroff: unarmed; no PMIC write\n");
		return NOTIFY_DONE;
	}
	control = board_pmic_guard();
	if (control < 0) {
		pr_err("tzx-poweroff: identity/control guard failed: %d\n", control);
		return NOTIFY_DONE;
	}
	bytes[0] = 0x27;
	bytes[1] = control | BIT(0);
	pr_emerg("tzx-poweroff: AXP717 soft off, REG27 %02x -> %02x\n",
		 control, bytes[1]);
	/* Preserve PWRON16s/PWROK configuration. Never set restart bit1. */
	ret = i2c_transfer(adapter, &msg, 1);
	if (ret != 1)
		pr_err("tzx-poweroff: soft-off transfer returned %d\n", ret);
	msleep(1000);
	pr_err("tzx-poweroff: power still present; continue to PSCI fallback\n");
	return NOTIFY_DONE;
}

static int __init start(void)
{
	int ret;

	if (!of_machine_is_compatible("tzx,p30a523"))
		return -ENODEV;
	adapter = i2c_get_adapter(0);
	if (!adapter)
		return -ENODEV;
	ret = board_pmic_guard();
	if (ret < 0)
		goto put_adapter;
	handler = register_sys_off_handler(SYS_OFF_MODE_POWER_OFF_PREPARE,
					   SYS_OFF_PRIO_DEFAULT,
					   poweroff_prepare, NULL);
	if (IS_ERR(handler)) {
		ret = PTR_ERR(handler);
		goto put_adapter;
	}
	pr_info("tzx-poweroff: AXP717 prepare handler armed=%u, REG27=%02x; no write performed\n",
		armed, ret);
	return 0;

put_adapter:
	i2c_put_adapter(adapter);
	return ret;
}

static void __exit stop(void)
{
	unregister_sys_off_handler(handler);
	i2c_put_adapter(adapter);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 AXP717 sleepable soft power-off, exact board guards");
