// SPDX-License-Identifier: GPL-2.0-only
/* Bounded test of PH6, the amplifier-enable candidate from two A523 boards. */
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio/machine.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/workqueue.h>

static bool arm;
module_param(arm, bool, 0400);
static unsigned int seconds = 60;
module_param(seconds, uint, 0400);
static struct platform_device *owner;
static struct gpio_desc *enable;
static void __iomem *pio;
static u32 saved_mux, saved_data;
static DEFINE_MUTEX(lock);
static struct delayed_work timeout_work;
static struct gpiod_lookup_table lookup = {
    .dev_id = "tzx-amp-probe",
    .table = { GPIO_LOOKUP("2000000.pinctrl", 230, "enable", GPIO_ACTIVE_HIGH), {} }
};

static void restore(void)
{
    mutex_lock(&lock);
    if (enable) {
        gpiod_set_value_cansleep(enable, 0);
        gpiod_put(enable);
        enable = NULL;
        writel((readl(pio + 0x160) & ~BIT(6)) | saved_data, pio + 0x160);
        writel((readl(pio + 0x150) & ~GENMASK(27, 24)) | saved_mux, pio + 0x150);
        pr_info("TZX AMP: PH6 test ended, original mux/data restored\n");
    }
    mutex_unlock(&lock);
}
static void timed_off(struct work_struct *work) { restore(); }
static int __init start(void)
{
    int ret;
    if (!arm || !of_machine_is_compatible("tzx,p30a523") || seconds < 5 || seconds > 120)
        return -EINVAL;
    pio = ioremap(0x02000000, 0x800);
    if (!pio) return -ENOMEM;
    saved_mux = readl(pio + 0x150) & GENMASK(27, 24);
    saved_data = readl(pio + 0x160) & BIT(6);
    if (saved_mux != 0 && saved_mux != (7 << 24) && saved_mux != (15 << 24)) {
        ret = -EBUSY;
        goto unmap;
    }
    gpiod_add_lookup_table(&lookup);
    owner = platform_device_register_simple("tzx-amp-probe", -1, NULL, 0);
    if (IS_ERR(owner)) { ret = PTR_ERR(owner); owner = NULL; goto remove_lookup; }
    enable = gpiod_get(&owner->dev, "enable", GPIOD_OUT_LOW);
    if (IS_ERR(enable)) { ret = PTR_ERR(enable); enable = NULL; goto unregister; }
    INIT_DELAYED_WORK(&timeout_work, timed_off);
    msleep(20);
    gpiod_set_value_cansleep(enable, 1);
    schedule_delayed_work(&timeout_work, seconds * HZ);
    pr_info("TZX AMP: candidate PH6 high for at most %u seconds\n", seconds);
    return 0;
unregister:
    platform_device_unregister(owner);
remove_lookup:
    gpiod_remove_lookup_table(&lookup);
unmap:
    iounmap(pio);
    return ret;
}
static void __exit stop(void)
{
    cancel_delayed_work_sync(&timeout_work);
    restore();
    platform_device_unregister(owner);
    gpiod_remove_lookup_table(&lookup);
    iounmap(pio);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Timed and reversible PH6 amplifier candidate test");
