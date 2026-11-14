// SPDX-License-Identifier: GPL-2.0-only
/*
 * TZX P30 A523 conservative CPUfreq bring-up.
 *
 * Only the two CPU mux registers' power-of-two divider fields are changed.
 * The already running 480 MHz PLLs, DSU and PMIC are never programmed here.
 * Register layout: Andre Przywara's A523 CPU CCU v3, 2026-09-25,
 * Message-ID: 20260925225112.14081-4-andre.przywara@arm.com.
 */
#include <linux/cpu.h>
#include <linux/cpufreq.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/spinlock.h>

#define TZX_CPU_CCU 0x08817000
#define TZX_PLL_FIELDS (GENMASK(21, 16) | GENMASK(15, 8) | GENMASK(2, 0))
#define TZX_DIV GENMASK(17, 16)
#define TZX_MUX GENMASK(26, 24)

static void __iomem *tzx_regs;
static DEFINE_SPINLOCK(tzx_lock);
static const u32 tzx_mux_offsets[] = {0x60, 0x64};
static const u32 tzx_pll_offsets[] = {0x04, 0x0c};
static u32 saved_mux[2];

static struct cpufreq_frequency_table tzx_frequencies[] = {
	{ .driver_data = 2, .frequency = 120000 },
	{ .driver_data = 1, .frequency = 240000 },
	{ .driver_data = 0, .frequency = 480000 },
	{ .frequency = CPUFREQ_TABLE_END },
};

static bool tzx_clock_is_known(unsigned int cluster)
{
	u32 pll = readl(tzx_regs + tzx_pll_offsets[cluster]);
	u32 mux = readl(tzx_regs + tzx_mux_offsets[cluster]);

	/* CPUB's baseline helper disables lock detection after it locks, so
	 * its lock status bit is not a persistent validity indicator. */
	return (pll & (BIT(31) | BIT(30) | BIT(27))) ==
		(BIT(31) | BIT(30) | BIT(27)) &&
	       (pll & TZX_PLL_FIELDS) == (20U << 8) &&
	       (mux & TZX_MUX) == (3U << 24);
}

static unsigned int tzx_get(unsigned int cpu)
{
	u32 mux;

	if (cpu >= 8 || !tzx_clock_is_known(cpu / 4))
		return 0;
	mux = readl(tzx_regs + tzx_mux_offsets[cpu / 4]);
	return 480000U >> ((mux & TZX_DIV) >> 16);
}

static int tzx_target_index(struct cpufreq_policy *policy, unsigned int index)
{
	unsigned int cluster = policy->cpu / 4;
	unsigned long flags;
	u32 before, after;
	int result = 0;

	if (cluster >= 2 || index >= ARRAY_SIZE(tzx_frequencies) - 1)
		return -EINVAL;
	spin_lock_irqsave(&tzx_lock, flags);
	if (!tzx_clock_is_known(cluster)) {
		result = -EIO;
		goto out;
	}
	before = readl(tzx_regs + tzx_mux_offsets[cluster]);
	after = (before & ~TZX_DIV) | (tzx_frequencies[index].driver_data << 16);
	writel(after, tzx_regs + tzx_mux_offsets[cluster]);
	if (readl(tzx_regs + tzx_mux_offsets[cluster]) != after) {
		writel(before, tzx_regs + tzx_mux_offsets[cluster]);
		result = -EIO;
	}
out:
	spin_unlock_irqrestore(&tzx_lock, flags);
	return result;
}

static int tzx_policy_init(struct cpufreq_policy *policy)
{
	unsigned int first = (policy->cpu / 4) * 4;
	unsigned int cpu;

	if (first >= 8 || !tzx_get(policy->cpu))
		return -ENODEV;
	cpumask_clear(policy->cpus);
	for (cpu = first; cpu < first + 4; cpu++)
		cpumask_set_cpu(cpu, policy->cpus);
	policy->shared_type = CPUFREQ_SHARED_TYPE_ALL;
	policy->freq_table = tzx_frequencies;
	policy->cpuinfo.transition_latency = 10000;
	return 0;
}

static struct cpufreq_driver tzx_driver = {
	.name = "tzx-a523-divider",
	.flags = CPUFREQ_CONST_LOOPS | CPUFREQ_HAVE_GOVERNOR_PER_POLICY,
	.verify = cpufreq_generic_frequency_table_verify,
	.target_index = tzx_target_index,
	.get = tzx_get,
	.init = tzx_policy_init,
};

static int __init tzx_cpufreq_init(void)
{
	unsigned int cluster;
	int ret;

	if (!of_machine_is_compatible("tzx,p30a523") || num_possible_cpus() != 8)
		return -ENODEV;
	tzx_regs = ioremap(TZX_CPU_CCU, 0x80);
	if (!tzx_regs)
		return -ENOMEM;
	for (cluster = 0; cluster < 2; cluster++) {
		saved_mux[cluster] = readl(tzx_regs + tzx_mux_offsets[cluster]);
		if (!tzx_clock_is_known(cluster) || (saved_mux[cluster] & TZX_DIV)) {
			pr_err("tzx-cpufreq: requires both clusters at the verified 480 MHz baseline\n");
			iounmap(tzx_regs);
			return -ENODEV;
		}
	}
	ret = cpufreq_register_driver(&tzx_driver);
	if (ret) {
		for (cluster = 0; cluster < 2; cluster++)
			writel(saved_mux[cluster], tzx_regs + tzx_mux_offsets[cluster]);
		iounmap(tzx_regs);
		return ret;
	}
	pr_info("tzx-cpufreq: two clusters, 120/240/480 MHz dividers; PLL/DSU/voltage unchanged\n");
	return 0;
}

static void __exit tzx_cpufreq_exit(void)
{
	unsigned int cluster;

	cpufreq_unregister_driver(&tzx_driver);
	for (cluster = 0; cluster < 2; cluster++)
		writel(saved_mux[cluster], tzx_regs + tzx_mux_offsets[cluster]);
	iounmap(tzx_regs);
	pr_info("tzx-cpufreq: restored both original 480 MHz divider registers\n");
}

module_init(tzx_cpufreq_init);
module_exit(tzx_cpufreq_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 A523 conservative CPUfreq divider bring-up");
