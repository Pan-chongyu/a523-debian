// SPDX-License-Identifier: GPL-2.0-only
/* A523 online CPU clock qualification at the existing 900 mV rails.
 * Register layout/mux bypass: Andre Przywara's CPU CCU v3 (2026-09-25).
 * Update/lock handshake: BSP as documented by Juan Manuel Lopez Carrillo,
 * orangepi-4a-mainline patches 0066/0070/0071. Worst-bin BSP OPP limits:
 * little <=792 MHz, big <=1008 MHz at 900 mV (patch 0069).
 * No PMIC/DSU/DRAM/backup-PLL writes. Both policies initially capped 480 MHz.
 */
#include <linux/clk.h>
#include <linux/arch_topology.h>
#include <linux/cpu.h>
#include <linux/cpufreq.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
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
static unsigned long saved_frequency_ref[8];
static int clock_fault;
module_param(clock_fault, int, 0444);
static struct clk *bypass;

static struct cpufreq_frequency_table little[] = {
    {.driver_data = (20 << 2) | 2, .frequency = 120000},
    {.driver_data = (20 << 2) | 1, .frequency = 240000},
    {.driver_data = 20 << 2, .frequency = 480000},
    {.driver_data = 25 << 2, .frequency = 600000},
    {.driver_data = 33 << 2, .frequency = 792000},
    {.frequency = CPUFREQ_TABLE_END},
};
static struct cpufreq_frequency_table big[] = {
    {.driver_data = (20 << 2) | 2, .frequency = 120000},
    {.driver_data = (20 << 2) | 1, .frequency = 240000},
    {.driver_data = 20 << 2, .frequency = 480000},
    {.driver_data = 25 << 2, .frequency = 600000},
    {.driver_data = 33 << 2, .frequency = 792000},
    {.driver_data = 42 << 2, .frequency = 1008000},
    {.frequency = CPUFREQ_TABLE_END},
};

static bool known(unsigned int cluster)
{
    u32 pll = readl(regs + pll_offsets[cluster]);
    u32 mux = readl(regs + mux_offsets[cluster]);
    unsigned int n = (pll & N) >> 8;

    return (pll & ENABLE) == ENABLE && !(pll & FIXED_DIV) &&
           (mux & MUX) == 3U << 24 &&
           (n == 20 || n == 25 || n == 33 || (cluster && n == 42));
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
    unsigned int cluster = policy->cpu / 4, value;
    int ret;

    if (cluster >= 2 || index >= (cluster ? ARRAY_SIZE(big) : ARRAY_SIZE(little)) - 1)
        return -EINVAL;
    value = policy->freq_table[index].driver_data;
    mutex_lock(&clock_lock);
    if (clock_fault || !known(cluster))
        ret = -EIO;
    else
        ret = select_clock(cluster, value >> 2, value & 3);
    if (ret)
        clock_fault = ret;
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
        WRITE_ONCE(per_cpu(capacity_freq_ref, cpu), first ? 1008000 : 792000);
    }
    policy->shared_type = CPUFREQ_SHARED_TYPE_ALL;
    policy->freq_table = first ? big : little;
    policy->max = 480000;
    policy->cpuinfo.transition_latency = 1000000;
    return 0;
}

static struct cpufreq_driver driver = {
    .name = "tzx-a523-safepll",
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
    for (i = 0; i < 8; i++)
        saved_frequency_ref[i] = READ_ONCE(per_cpu(capacity_freq_ref, i));
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
    ret = cpufreq_register_driver(&driver);
    if (ret) {
        for (i = 0; i < 8; i++)
            WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);
        goto unmap;
    }
    pr_info("tzx-safepll: fixed-voltage tables little 120..792, big 120..1008 MHz; initial limits 480 MHz\n");
    return 0;
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

    cpufreq_unregister_driver(&driver);
    restore();
    for (i = 0; i < 8; i++)
        WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);
    iounmap(regs);
    clk_disable_unprepare(bypass);
    clk_put(bypass);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("A523 CPU PLL qualification within universal 900 mV OPP limits");
