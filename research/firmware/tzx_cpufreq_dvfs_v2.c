// SPDX-License-Identifier: GPL-2.0-only
/* A523 voltage-aware CPU performance with bounded DCDC1 ramps.
 * Register layout/mux bypass: Andre Przywara's CPU CCU v3 (2026-09-25).
 * Update/lock handshake: BSP as documented by Juan Manuel Lopez Carrillo,
 * orangepi-4a-mainline patches 0066/0070/0071. Worst-bin BSP OPP limits:
 * little <=792 MHz, big <=1008 MHz at 900 mV (patch 0069).
 * Only CPU DCDC1 writes; no DSU/DRAM/backup-PLL writes. Initial cap 480 MHz.
 */
#include <linux/clk.h>
#include <linux/arch_topology.h>
#include <linux/cpu.h>
#include <linux/cpufreq.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/i2c.h>
#include <linux/jiffies.h>
#include <linux/pm_qos.h>
#include <linux/workqueue.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/nvmem-consumer.h>
#include <linux/topology.h>
extern void tzx_topology_refresh_capacity(void);
#include <dt-bindings/clock/sun55i-a523-ccu.h>

#define DIV GENMASK(17, 16)
#define MUX GENMASK(26, 24)
#define N GENMASK(15, 8)
#define FIXED_DIV (GENMASK(21, 16) | GENMASK(2, 0))
#define ENABLE (BIT(31) | BIT(30) | BIT(27))
#define UPDATE BIT(26)
#define LOCK_ENABLE BIT(29)
#define LOCKED BIT(28)
static void __iomem *regs;
static DEFINE_MUTEX(clock_lock);
static const u32 pll_offsets[] = {4, 12}, mux_offsets[] = {0x60, 0x64};
static u32 saved_pll[2], saved_mux[2];
static unsigned long saved_frequency_ref[8], saved_capacity[8];
static unsigned int sid_dvfs_word, vf_index=0x0300;
module_param(sid_dvfs_word,uint,0444);
module_param(vf_index,uint,0444);
/* BSP V0.71: 0x48 >> 4 = combi 4 -> vf0300. Its 1992 MHz OPP is zero.
 * Read only the public DVFS word through the nvmem provider; never write SID. */
static int check_speed_bin(void)
{
    struct nvmem_device *sid=nvmem_device_find("sunxi-sid0",device_match_name);
    __le32 word;
    unsigned int combi;
    int ret;
    if(IS_ERR(sid))return PTR_ERR(sid);
    ret=nvmem_device_read(sid,0x48,sizeof(word),&word);
    nvmem_device_put(sid);
    if(ret!=sizeof(word))return ret<0?ret:-EIO;
    sid_dvfs_word=le32_to_cpu(word);
    combi=(sid_dvfs_word>>12)&0xff;
    if(!combi)combi=(sid_dvfs_word>>4)&0xff;
    return combi==0x04 ? 0 : -ENODEV;
}
static int clock_fault;
module_param(clock_fault, int, 0444);
static struct clk *bypass;
static struct i2c_adapter *pmic;
static const u16 pmic_address[] = {0x34, 0x36};
static const u8 voltage_register[] = {0x83, 0x13};
static u8 initial_voltage[2];
static unsigned int rail_mv[2] = {900, 900};
module_param_array(rail_mv, uint, NULL, 0444);
static struct cpufreq_policy *lease_policy[2];
static struct freq_qos_request lease_qos[2];
static struct delayed_work lease_work;
static unsigned long lease_deadline;
static unsigned int lease_seconds = 30, lease_active;
static bool stopping, ready;
module_param(lease_seconds, uint, 0444);
module_param(lease_active, uint, 0444);

static int pmic_read(unsigned int cluster, u8 reg, u8 *value)
{
    struct i2c_msg messages[] = {
        {.addr=pmic_address[cluster], .len=1, .buf=&reg},
        {.addr=pmic_address[cluster], .flags=I2C_M_RD, .len=1, .buf=value},
    };
    int ret = i2c_transfer(pmic, messages, 2);
    return ret == 2 ? 0 : ret < 0 ? ret : -EIO;
}

/* Both identified DCDC1 selectors are 500mV + 10mV*n in this range.
 * Only 0x34:0x83 and 0x36:0x13 are writable here. DVM bit 7 is preserved.
 * CPU clocks are never raised before readback and the settling interval. */
static int set_voltage(unsigned int cluster, unsigned int millivolts)
{
    u8 observed, wanted, pair[2], step;
    struct i2c_msg message = {.addr=pmic_address[cluster], .len=2, .buf=pair};
    int ret;
    if (millivolts < 900 || millivolts > 1150 || millivolts % 10)
        return -EINVAL;
    ret = pmic_read(cluster, voltage_register[cluster], &observed);
    if (ret)
        return ret;
    if ((observed & 0x80) != (initial_voltage[cluster] & 0x80) ||
        (observed & 0x7f) < 40 || (observed & 0x7f) > 65)
        return -EPERM;
    wanted = (millivolts - 500) / 10;
    while ((observed & 0x7f) != wanted) {
        step = observed + ((observed & 0x7f) < wanted ? 1 : -1);
        pair[0] = voltage_register[cluster];
        pair[1] = step;
        ret = i2c_transfer(pmic, &message, 1);
        if (ret != 1)
            return ret < 0 ? ret : -EIO;
        usleep_range(200, 350);
        ret = pmic_read(cluster, voltage_register[cluster], &observed);
        if (ret || observed != step)
            return ret ? ret : -EIO;
        WRITE_ONCE(rail_mv[cluster], 500 + (observed & 0x7f) * 10);
    }
    usleep_range(500, 700);
    return 0;
}

static unsigned int required_mv(unsigned int cluster, unsigned int khz)
{
    if (!cluster) {
        if (khz > 1224000) return 1150;
        if (khz > 1008000) return 1050;
        if (khz > 792000) return 960;
    } else {
        if (khz > 1680000) return 1150;
        if (khz > 1584000) return 1100;
        if (khz > 1488000) return 1050;
        if (khz > 1344000) return 1000;
        if (khz > 1200000) return 960;
        if (khz > 1008000) return 920;
    }
    return 900;
}

static int renew_set(const char *value, const struct kernel_param *param)
{
    unsigned int requested;
    int ret = kstrtouint(value, 0, &requested), i;
    if (ret || requested != 1)
        return -EINVAL;
    mutex_lock(&clock_lock);
    if (!ready || stopping || clock_fault) {
        mutex_unlock(&clock_lock);
        return -EIO;
    }
    lease_deadline = jiffies + lease_seconds * HZ;
    WRITE_ONCE(lease_active, 1);
    mutex_unlock(&clock_lock);
    for (i = 0; i < 2; i++)
        freq_qos_update_request(&lease_qos[i], i ? 1800000 : 1416000);
    return 0;
}
static const struct kernel_param_ops renew_ops = {.set=renew_set, .get=param_get_uint};
module_param_cb(renew, &renew_ops, &lease_active, 0600);

static void check_lease(struct work_struct *work)
{
    int i;
    bool expired;
    mutex_lock(&clock_lock);
    expired = clock_fault || time_after_eq(jiffies, lease_deadline);
    if (expired)
        WRITE_ONCE(lease_active, 0);
    mutex_unlock(&clock_lock);
    if (expired)
        for (i = 0; i < 2; i++)
            freq_qos_update_request(&lease_qos[i], 480000);
    if (!READ_ONCE(stopping))
        schedule_delayed_work(&lease_work, msecs_to_jiffies(200));
}

static struct cpufreq_frequency_table little[] = {
    {.driver_data=(20 << 2) | 2, .frequency=120000},
    {.driver_data=(20 << 2) | 1, .frequency=240000},
    {.driver_data=(20 << 2) | 0, .frequency=480000},
    {.driver_data=(25 << 2) | 0, .frequency=600000},
    {.driver_data=(33 << 2) | 0, .frequency=792000},
    {.driver_data=(42 << 2) | 0, .frequency=1008000},
    {.driver_data=(51 << 2) | 0, .frequency=1224000},
    {.driver_data=(59 << 2) | 0, .frequency=1416000},
    {.frequency=CPUFREQ_TABLE_END},
};

static struct cpufreq_frequency_table big[] = {
    {.driver_data=(20 << 2) | 2, .frequency=120000},
    {.driver_data=(20 << 2) | 1, .frequency=240000},
    {.driver_data=(20 << 2) | 0, .frequency=480000},
    {.driver_data=(25 << 2) | 0, .frequency=600000},
    {.driver_data=(33 << 2) | 0, .frequency=792000},
    {.driver_data=(42 << 2) | 0, .frequency=1008000},
    {.driver_data=(50 << 2) | 0, .frequency=1200000},
    {.driver_data=(56 << 2) | 0, .frequency=1344000},
    {.driver_data=(62 << 2) | 0, .frequency=1488000},
    {.driver_data=(66 << 2) | 0, .frequency=1584000},
    {.driver_data=(70 << 2) | 0, .frequency=1680000},
    {.driver_data=(75 << 2) | 0, .frequency=1800000},
    {.frequency=CPUFREQ_TABLE_END},
};

static bool known(unsigned int cluster)
{
    u32 pll = readl(regs + pll_offsets[cluster]);
    u32 mux = readl(regs + mux_offsets[cluster]);
    unsigned int n = (pll & N) >> 8;

    return (pll & ENABLE) == ENABLE && !(pll & FIXED_DIV) &&
           (mux & MUX) == 3U << 24 &&
           (n == 20 || n == 25 || n == 33 || n == 42 ||
            (!cluster && (n == 51 || n == 59)) ||
            (cluster && (n == 50 || n == 56 || n == 62 || n == 66 || n == 70 || n == 75)));
}

static unsigned int get(unsigned int cpu)
{
    u32 pll, mux;

    if (cpu >= 8)
        return 0;
    mux = readl(regs + mux_offsets[cpu / 4]);
    if ((mux & MUX) == 4U << 24)
        return 600000;
    if (!known(cpu / 4))
        return 0;
    pll = readl(regs + pll_offsets[cpu / 4]);
    return (24000U * ((pll & N) >> 8)) >> ((mux & DIV) >> 16);
}

/* Caller holds a sleepable mutex. The cluster runs from the fixed 600 MHz
 * source throughout both polls; IRQs stay enabled, other clusters can run. */
static int commit(unsigned int cluster, u32 value)
{
    void __iomem *address = regs + pll_offsets[cluster];
    u32 observed;
    int ret;

    writel(value | ENABLE | LOCK_ENABLE | UPDATE, address);
    ret = readl_poll_timeout(address, observed, !(observed & UPDATE), 10, 10000);
    if (ret)
        return ret;
    /* Re-arm detection, as in the sunxi CPU PLL POST_RATE_CHANGE notifier. */
    writel(readl(address) & ~LOCK_ENABLE, address);
    writel(readl(address) | LOCK_ENABLE, address);
    return readl_poll_timeout(address, observed, observed & LOCKED, 10, 70000);
}

static int select_clock(unsigned int cluster, unsigned int n, unsigned int div)
{
    u32 old_pll, old_mux, final_mux, observed;
    int ret;

    old_pll = readl(regs + pll_offsets[cluster]);
    old_mux = readl(regs + mux_offsets[cluster]);
    final_mux = (old_mux & ~(MUX | DIV)) | (3U << 24) | (div << 16);
    if (((old_pll & N) >> 8) == n) {
        writel(final_mux, regs + mux_offsets[cluster]);
        return readl(regs + mux_offsets[cluster]) == final_mux ? 0 : -EIO;
    }
    writel((old_mux & ~MUX) | (4U << 24), regs + mux_offsets[cluster]);
    observed = readl(regs + mux_offsets[cluster]);
    if ((observed & MUX) != 4U << 24)
        return -EIO;
    udelay(1);
    ret = commit(cluster, (old_pll & ~N) | (n << 8));
    if (ret) {
        /* Never remux a consumer onto an unlocked PLL. Leave a failed
         * restore on the known 600 MHz bypass and report the failure. */
        if (!commit(cluster, old_pll))
            writel(old_mux, regs + mux_offsets[cluster]);
        return ret;
    }
    if (((readl(regs + pll_offsets[cluster]) & N) >> 8) != n)
        return -EIO;
    writel(final_mux, regs + mux_offsets[cluster]);
    udelay(1);
    return readl(regs + mux_offsets[cluster]) == final_mux ? 0 : -EIO;
}

static int target_index(struct cpufreq_policy *policy, unsigned int index)
{
    unsigned int cluster = policy->cpu / 4, value, millivolts;
    int ret;

    if (cluster >= 2 || index >= (cluster ? ARRAY_SIZE(big) : ARRAY_SIZE(little)) - 1)
        return -EINVAL;
    value = policy->freq_table[index].driver_data;
    mutex_lock(&clock_lock);
    if (clock_fault || !known(cluster))
        ret = -EIO;
    else {
        millivolts = required_mv(cluster, policy->freq_table[index].frequency);
        if (policy->freq_table[index].frequency > 480000 &&
            (!lease_active || time_after_eq(jiffies, lease_deadline))) {
            ret = -EAGAIN;
            goto unlock;
        }
        ret = 0;
        if (millivolts > rail_mv[cluster])
            ret = set_voltage(cluster, millivolts);
        if (!ret)
            ret = select_clock(cluster, value >> 2, value & 3);
        if (!ret && millivolts < rail_mv[cluster])
            ret = set_voltage(cluster, millivolts);
    }
    if (ret)
        clock_fault = ret;
unlock:
    mutex_unlock(&clock_lock);
    return ret;
}

static int policy_init(struct cpufreq_policy *policy)
{
    unsigned int first = (policy->cpu / 4) * 4, cpu;

    if (first >= 8 || !known(first / 4))
        return -ENODEV;
    cpumask_clear(policy->cpus);
    for (cpu = first; cpu < first + 4; cpu++) {
        cpumask_set_cpu(cpu, policy->cpus);
        /* The early arch-topology notifier unregisters after the first
         * driver's policies. An online replacement must refresh its
         * exported reference, otherwise schedutil stays capped at 480. */
        WRITE_ONCE(per_cpu(capacity_freq_ref, cpu), first ? 1800000 : 1416000);
        /* Same normalization as arch_topology: BSP DMIPS/MHz * max kHz.
         * cpu_scale is the kernel's exported capacity interface. A queued
         * topology refresh follows driver registration, outside its locks. */
        WRITE_ONCE(per_cpu(cpu_scale, cpu), first ? 1024 : 922UL*1416000/1800000);
    }
    policy->shared_type = CPUFREQ_SHARED_TYPE_ALL;
    policy->freq_table = first ? big : little;
    policy->max = 480000;
    /* 25 x 10mV steps plus I2C/readback/settling. Avoid flooding the
     * sleepable slow-switch path with a fictitious 1ms transition budget. */
    policy->cpuinfo.transition_latency = 12000000;
    return 0;
}

static struct cpufreq_driver driver = {
    .name = "tzx-a523-dvfs2",
    .flags = CPUFREQ_CONST_LOOPS | CPUFREQ_HAVE_GOVERNOR_PER_POLICY,
    .verify = cpufreq_generic_frequency_table_verify,
    .target_index = target_index,
    .get = get,
    .init = policy_init,
};

static void restore(void)
{
    int i;

    mutex_lock(&clock_lock);
    for (i = 0; i < 2; i++) {
        if (!select_clock(i, 20, 0)) {
            /* Only lock-enable was changed in addition to N. Restore it
             * after the original rate is locked and feeding the CPUs. */
            writel((readl(regs + pll_offsets[i]) & ~LOCK_ENABLE) |
                   (saved_pll[i] & LOCK_ENABLE), regs + pll_offsets[i]);
            writel(saved_mux[i], regs + mux_offsets[i]);
            if (set_voltage(i, 900))
                pr_err("tzx-dvfs: CPU%d 900mV restore failed\n", i);
        } else {
            pr_err("tzx-safepll: cluster %d restore failed, retaining 600 MHz bypass\n", i);
        }
    }
    mutex_unlock(&clock_lock);
}

static int __init start(void)
{
    struct device_node *node;
    int ret, i;

    if (!of_machine_is_compatible("tzx,p30a523") || num_possible_cpus() != 8)
        return -ENODEV;
    ret=check_speed_bin();
    if(ret)return ret;
    for (i = 0; i < 8; i++) {
        saved_frequency_ref[i] = READ_ONCE(per_cpu(capacity_freq_ref, i));
        saved_capacity[i] = READ_ONCE(per_cpu(cpu_scale,i));
    }
    node = of_find_node_by_path("/soc/clock-controller@2001000");
    if (!node)
        return -ENODEV;
    {
        struct of_phandle_args spec = {};
        spec.np = node;
        spec.args_count = 1;
        spec.args[0] = CLK_PLL_PERIPH0_600M;
        bypass = of_clk_get_from_provider(&spec);
    }
    of_node_put(node);
    if (IS_ERR(bypass))
        return PTR_ERR(bypass);
    if (clk_get_rate(bypass) != 600000000) {
        ret = -ENODEV;
        goto put_clk;
    }
    ret = clk_prepare_enable(bypass);
    if (ret)
        goto put_clk;
    regs = ioremap(0x08817000, 0x80);
    if (!regs) {
        ret = -ENOMEM;
        goto disable;
    }
    for (i = 0; i < 2; i++) {
        saved_pll[i] = readl(regs + pll_offsets[i]);
        saved_mux[i] = readl(regs + mux_offsets[i]);
        if (!known(i) || ((saved_pll[i] & N) >> 8) != 20 || (saved_mux[i] & DIV)) {
            ret = -ENODEV;
            goto unmap;
        }
    }
    pmic = i2c_get_adapter(0);
    if (!pmic) { ret = -ENODEV; goto unmap; }
    for (i = 0; i < 2; i++) {
        u8 id;
        ret = pmic_read(i, 3, &id);
        if (ret || id != (i ? 0x49 : 0xff)) { ret = -ENODEV; goto put_i2c; }
        ret = pmic_read(i, voltage_register[i], &initial_voltage[i]);
        if (ret || (initial_voltage[i] & 0x7f) != 40) { ret = -EPERM; goto put_i2c; }
    }
    if (lease_seconds < 3 || lease_seconds > 60) { ret = -EINVAL; goto put_i2c; }
    lease_deadline = jiffies;
    ret = cpufreq_register_driver(&driver);
    if (ret) {
        for (i = 0; i < 8; i++) {
            WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);
            WRITE_ONCE(per_cpu(cpu_scale,i),saved_capacity[i]);
        }
        goto put_i2c;
    }
    for (i = 0; i < 2; i++) {
        lease_policy[i] = cpufreq_cpu_get(i * 4);
        ret = freq_qos_add_request(&lease_policy[i]->constraints, &lease_qos[i], FREQ_QOS_MAX, 480000);
        if (ret < 0) goto remove_qos;
    }
    tzx_topology_refresh_capacity();
    ready = true;
    INIT_DELAYED_WORK(&lease_work, check_lease);
    schedule_delayed_work(&lease_work, msecs_to_jiffies(200));
    pr_info("tzx-dvfs: DCDC1-only DVFS vf0300 little 120..1416 big 120..1800 MHz; initial 480, renewable lease\n");
    return 0;
remove_qos:
    while (i--) {
        freq_qos_remove_request(&lease_qos[i]);
        cpufreq_cpu_put(lease_policy[i]);
    }
    cpufreq_unregister_driver(&driver);
put_i2c:
    i2c_put_adapter(pmic);
unmap:
    iounmap(regs);
disable:
    clk_disable_unprepare(bypass);
put_clk:
    clk_put(bypass);
    return ret;
}

static void __exit stop(void)
{
    int i;

    WRITE_ONCE(stopping, true);
    cancel_delayed_work_sync(&lease_work);
    for (i = 0; i < 2; i++) {
        freq_qos_remove_request(&lease_qos[i]);
        cpufreq_cpu_put(lease_policy[i]);
    }
    cpufreq_unregister_driver(&driver);
    restore();
    i2c_put_adapter(pmic);
    for (i = 0; i < 8; i++) {
        WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);
        WRITE_ONCE(per_cpu(cpu_scale,i),saved_capacity[i]);
    }
    tzx_topology_refresh_capacity();
    iounmap(regs);
    clk_disable_unprepare(bypass);
    clk_put(bypass);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("A523 CPU DCDC1 DVFS with readback, settling, thermal policy and lease");
