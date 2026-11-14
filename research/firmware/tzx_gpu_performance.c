// SPDX-License-Identifier: GPL-2.0-only
/* Online, leased GPU performance on the corrected A523 maskdiv clock.
 * Only fixed periph0 parents at the existing voltage; no PLL/PMIC writes.
 * Expired userspace lease, sensor failure or >=75C returns to 200 MHz.
 */
#include <linux/clk.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/thermal.h>
#include <linux/workqueue.h>

static struct device *gpu;
static struct clk *clock;
static void __iomem *ccu;
static struct thermal_zone_device *sensors[5];
static const char * const sensor_names[] = {
    "cpu-big-thermal", "cpu-little-thermal", "gpu-thermal",
    "npu-thermal", "ddr-thermal",
};
static DEFINE_MUTEX(lock);
static struct delayed_work monitor;
static unsigned long deadline;
static unsigned int requested_mhz = 200, actual_mhz = 200;
static unsigned int lease_seconds = 30;
static int first_trip = 65000, second_trip = 70000;
static int temperature_mc, fault;
static bool ready, stopping, clock_valid, active_only = true;
module_param(lease_seconds, uint, 0444);
module_param(first_trip, int, 0444);
module_param(second_trip, int, 0444);
module_param(active_only, bool, 0444);
module_param(actual_mhz, uint, 0444);
module_param(temperature_mc, int, 0444);
module_param(fault, int, 0444);

static int set_clock(unsigned int mhz)
{
    static const struct { unsigned int mhz, mux; } rates[] = {
        {200, 5}, {300, 4}, {400, 3}, {600, 2},
    };
    unsigned int i;
    u32 reg;
    int ret;

    for (i = 0; i < ARRAY_SIZE(rates); i++)
        if (rates[i].mhz == mhz)
            break;
    if (i == ARRAY_SIZE(rates))
        return -EINVAL;
    if (clk_get_rate(clock) != mhz * 1000000UL) {
        ret = clk_set_rate(clock, mhz * 1000000UL);
        if (ret)
            return ret;
    }
    reg = readl(ccu + 0x670);
    if (clk_get_rate(clock) != mhz * 1000000UL ||
        ((reg >> 24) & 7) != rates[i].mux || (reg & 15))
        return -EIO;
    WRITE_ONCE(actual_mhz, mhz);
    return 0;
}

static int update_locked(void)
{
    unsigned int target = 200;
    int maximum = 0, value, ret, i;

    for (i = 0; i < ARRAY_SIZE(sensors); i++) {
        ret = thermal_zone_get_temp(sensors[i], &value);
        if (ret || value <= 0 || value > 125000) {
            fault = ret ? ret : -ENODATA;
            break;
        }
        maximum = max(maximum, value);
    }
    temperature_mc = maximum;
    if (maximum >= 75000)
        fault = -EOVERFLOW;
    if (!fault && time_before(jiffies, deadline) &&
        (!active_only || pm_runtime_active(gpu))) {
        target = requested_mhz;
        if (maximum >= second_trip)
            target = 200;
        else if (maximum >= first_trip)
            target = min(target, 400U);
    }
    ret = set_clock(target);
    if (ret) {
        fault = ret;
        set_clock(200);
    }
    return ret;
}

static int request_set(const char *value, const struct kernel_param *kp)
{
    unsigned int mhz;
    int ret = kstrtouint(value, 0, &mhz);

    if (ret)
        return ret;
    if (mhz != 200 && mhz != 300 && mhz != 400 && mhz != 600)
        return -EINVAL;
    mutex_lock(&lock);
    if (fault && mhz != 200) {
        ret = -EIO;
        goto out;
    }
    requested_mhz = mhz;
    deadline = jiffies + lease_seconds * HZ;
    if (ready)
        ret = update_locked();
out:
    mutex_unlock(&lock);
    return ret;
}

static const struct kernel_param_ops request_ops = {
    .set = request_set, .get = param_get_uint,
};
module_param_cb(requested_mhz, &request_ops, &requested_mhz, 0644);

static void tick(struct work_struct *work)
{
    mutex_lock(&lock);
    update_locked();
    if (!stopping)
        schedule_delayed_work(&monitor, msecs_to_jiffies(200));
    mutex_unlock(&lock);
}

static void cleanup(void)
{
    int i;

    if (clock) {
        if (clock_valid)
            set_clock(200);
        clk_put(clock);
    }
    for (i = 0; i < ARRAY_SIZE(sensors); i++)
        if (sensors[i])
            put_device(thermal_zone_device(sensors[i]));
    if (ccu)
        iounmap(ccu);
    if (gpu)
        put_device(gpu);
}

static int __init start(void)
{
    int i, ret;

    if (!of_machine_is_compatible("tzx,p30a523"))
        return -ENODEV;
    if (lease_seconds < 5 || lease_seconds > 120 ||
        first_trip < 30000 || first_trip > 65000 ||
        second_trip <= first_trip || second_trip > 70000 || requested_mhz != 200)
        return -EINVAL;
    gpu = bus_find_device_by_name(&platform_bus_type, NULL, "1800000.gpu");
    if (!gpu || !device_is_bound(gpu)) {
        ret = -ENODEV;
        goto fail;
    }
    clock = clk_get(gpu, NULL);
    if (IS_ERR(clock)) {
        ret = PTR_ERR(clock);
        clock = NULL;
        goto fail;
    }
    ccu = ioremap(0x02001000, 0x1000);
    if (!ccu) {
        ret = -ENOMEM;
        goto fail;
    }
    if (clk_get_rate(clock) != 200000000 ||
        (readl(ccu + 0x670) & 0x0700000f) != 0x05000000) {
        ret = -ENODEV;
        goto fail;
    }
    for (i = 0; i < ARRAY_SIZE(sensors); i++) {
        sensors[i] = thermal_zone_get_zone_by_name(sensor_names[i]);
        if (IS_ERR(sensors[i])) {
            ret = PTR_ERR(sensors[i]);
            sensors[i] = NULL;
            goto fail;
        }
        get_device(thermal_zone_device(sensors[i]));
    }
    if (clk_round_rate(clock, 300000000) != 300000000 ||
        clk_round_rate(clock, 400000000) != 400000000 ||
        clk_round_rate(clock, 600000000) != 600000000) {
        ret = -EINVAL;
        goto fail;
    }
    clock_valid = true;
    mutex_lock(&lock);
    ret = update_locked();
    ready = !ret;
    mutex_unlock(&lock);
    if (ret || fault) {
        ret = ret ? ret : fault;
        goto fail;
    }
    INIT_DELAYED_WORK(&monitor, tick);
    schedule_delayed_work(&monitor, msecs_to_jiffies(200));
    pr_info("tzx-gpu-performance: fixed parents 200/300/400/600 MHz, %us lease, thermal caps %d/%d mC\n",
            lease_seconds, first_trip, second_trip);
    return 0;
fail:
    cleanup();
    return ret;
}

static void __exit stop(void)
{
    mutex_lock(&lock);
    stopping = true;
    ready = false;
    mutex_unlock(&lock);
    cancel_delayed_work_sync(&monitor);
    cleanup();
    pr_info("tzx-gpu-performance: removed; restored 200 MHz\n");
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Leased, thermal-guarded A523 fixed-parent GPU performance without voltage writes");
