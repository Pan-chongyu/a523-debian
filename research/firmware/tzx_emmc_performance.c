// SPDX-License-Identifier: GPL-2.0-only
/* Leased DDR52 clocks on this exact eMMC, using its existing host driver.
 * Same host-claim and set_ios path as drivers/mmc/core/debugfs.c clock.
 * No CMD6, voltage, bus-width, tuning, raw controller or partition writes.
 */
#include <linux/delay.h>
#include <linux/jiffies.h>
#include <linux/mmc/host.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/workqueue.h>
#include "core.h"

static struct platform_device *device;
static struct mmc_host *host;
static DEFINE_MUTEX(lock);
static struct delayed_work monitor;
static unsigned long deadline;
static unsigned int original_limit, original_clock, requested_mhz = 25;
static unsigned int actual_hz, lease_seconds = 30;
static u32 initial_errors[MMC_ERR_MAX];
static bool ready, stopping;
static int fault;
module_param(actual_hz, uint, 0444);
module_param(fault, int, 0444);
module_param(lease_seconds, uint, 0444);

static bool same_mode(void)
{
    return host->ios.power_mode == MMC_POWER_ON &&
           host->ios.timing == MMC_TIMING_MMC_DDR52 &&
           host->ios.bus_width == MMC_BUS_WIDTH_8 &&
           host->ios.signal_voltage == MMC_SIGNAL_VOLTAGE_180;
}

/* Caller holds this module's mutex. mmc_claim_host also resumes its parent.
 * mmc_set_clock() is not exported; its exact set_ios wrapper is used here. */
static int set_clock(unsigned int mhz)
{
    int ret = 0;

    mmc_claim_host(host);
    if (!same_mode()) {
        ret = -EPERM;
        goto release;
    }
    host->f_max = mhz == 25 ? original_limit : 52000000;
    if (host->ios.clock != mhz * 1000000U) {
        host->ios.clock = mhz * 1000000U;
        host->ops->set_ios(host, &host->ios);
    }
    actual_hz = host->actual_clock;
    if (!actual_hz || actual_hz > mhz * 1000000U)
        ret = -EIO;
release:
    mmc_release_host(host);
    return ret;
}

static int request_set(const char *value, const struct kernel_param *param)
{
    unsigned int mhz;
    int ret;

    ret = kstrtouint(value, 0, &mhz);
    if (ret)
        return ret;
    if (mhz != 25 && mhz != 33 && mhz != 40 && mhz != 50 && mhz != 52)
        return -EINVAL;
    mutex_lock(&lock);
    if (!ready || stopping || (fault && mhz != 25)) {
        ret = -EIO;
        goto unlock;
    }
    deadline = jiffies + lease_seconds * HZ;
    ret = set_clock(mhz);
    if (ret) {
        fault = ret;
        set_clock(25);
    } else {
        requested_mhz = mhz;
    }
unlock:
    mutex_unlock(&lock);
    return ret;
}

static const struct kernel_param_ops request_ops = {
    .set = request_set, .get = param_get_uint,
};
module_param_cb(requested_mhz, &request_ops, &requested_mhz, 0600);

static void check_lease(struct work_struct *work)
{
    unsigned int i;

    mutex_lock(&lock);
    for (i = 0; i < MMC_ERR_MAX; i++)
        if (READ_ONCE(host->err_stats[i]) != initial_errors[i])
            fault = -EIO;
    if ((fault || time_after_eq(jiffies, deadline)) &&
        (READ_ONCE(host->ios.clock) != original_clock ||
         READ_ONCE(host->f_max) != original_limit)) {
        if (set_clock(25))
            fault = -EIO;
    }
    if (!stopping)
        schedule_delayed_work(&monitor, msecs_to_jiffies(200));
    mutex_unlock(&lock);
}

static int __init start(void)
{
    static const u32 cid[] = {0x3e01ff55, 0x454d2020, 0x20102091, 0x70281b59};
    struct device_node *node;
    unsigned int i;
    int ret = -ENODEV;

    if (!of_machine_is_compatible("tzx,p30a523") || lease_seconds < 3 || lease_seconds > 60)
        return -EINVAL;
    node = of_find_node_by_path("/soc/mmc@4022000");
    if (!node)
        return -ENODEV;
    device = of_find_device_by_node(node);
    of_node_put(node);
    if (!device)
        return -ENODEV;
    host = platform_get_drvdata(device);
    if (!host || strcmp(mmc_hostname(host), "mmc0"))
        goto put;
    mmc_claim_host(host);
    if (!host->card || !mmc_card_mmc(host->card) || !same_mode() ||
        host->f_max != 25000000 || host->ios.clock != 25000000 ||
        host->actual_clock != 25000000 || host->card->ext_csd.hs_max_dtr != 52000000 ||
        host->card->ext_csd.sectors != 244318208)
        goto release;
    for (i = 0; i < ARRAY_SIZE(cid); i++)
        if (host->card->raw_cid[i] != cid[i])
            goto release;
    for (i = 0; i < MMC_ERR_MAX; i++) {
        initial_errors[i] = READ_ONCE(host->err_stats[i]);
        if (initial_errors[i])
            goto release;
    }
    original_limit = host->f_max;
    original_clock = host->ios.clock;
    actual_hz = host->actual_clock;
    deadline = jiffies;
    ready = true;
    mmc_release_host(host);
    INIT_DELAYED_WORK(&monitor, check_lease);
    schedule_delayed_work(&monitor, msecs_to_jiffies(200));
    pr_info("tzx-emmc-performance: exact CID, DDR52/8bit/1.8V, baseline 25MHz; lease %us\n", lease_seconds);
    return 0;
release:
    mmc_release_host(host);
put:
    put_device(&device->dev);
    return ret;
}

static void __exit stop(void)
{
    mutex_lock(&lock);
    stopping = true;
    mutex_unlock(&lock);
    cancel_delayed_work_sync(&monitor);
    mutex_lock(&lock);
    if (same_mode() && set_clock(25))
        pr_err("tzx-emmc-performance: baseline clock restore failed\n");
    WRITE_ONCE(host->f_max, original_limit);
    mutex_unlock(&lock);
    put_device(&device->dev);
    pr_info("tzx-emmc-performance: original 25MHz limit restored\n");
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Leased TZX eMMC DDR52 clock qualification without mode or voltage changes");
