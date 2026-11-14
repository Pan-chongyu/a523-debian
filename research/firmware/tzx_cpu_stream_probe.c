// SPDX-License-Identifier: GPL-2.0-only
/* Read-only A55 r2p0 register diagnostic. No clock/voltage/register writes.
 * The retired EL1 write experiment is preserved in build/cpu-stream-rejected.
 * Documented streaming thresholds must be tested in a staged EL3 firmware.
 */
#include <linux/cpu.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/smp.h>
#include <asm/barrier.h>
#include <asm/cputype.h>
#include <asm/sysreg.h>

static bool disable_streaming;
module_param(disable_streaming, bool, 0400);
static atomic_t invalid = ATOMIC_INIT(0);

static u64 extended(void)
{
    u64 value;
    asm volatile("mrs %0, S3_0_C15_C1_4" : "=r" (value));
    return value;
}

static void snapshot(void *unused)
{
    unsigned int cpu = smp_processor_id();
    u32 midr = read_cpuid_id();
    u64 auxiliary, control;
    if (cpu >= 8 || midr != 0x412fd050) {
        atomic_set(&invalid, 1);
        return;
    }
    asm volatile("mrs %0, S3_0_C15_C1_0" : "=r" (auxiliary));
    control = extended();
    pr_info("tzx-cpu-stream: cpu%u midr=%08x cpuectlr=%016llx cpuactlr=%016llx tcr=%016llx mair=%016llx\n",
            cpu, midr, control, auxiliary, read_sysreg(tcr_el1), read_sysreg(mair_el1));
}

static int __init stream_init(void)
{
    /* Retired: the 2026-11-12 trial faulted exactly at the MSR. Reading is
     * supported, but this firmware has not granted a working EL1 write path.
     * Use a separately staged EL3 boot candidate for further comparisons. */
    if (disable_streaming)
        return -EOPNOTSUPP;
    if (!of_machine_is_compatible("tzx,p30a523") || num_online_cpus() != 8)
        return -ENODEV;
    cpus_read_lock();
    on_each_cpu(snapshot, NULL, 1);
    cpus_read_unlock();
    return atomic_read(&invalid) ? -EIO : 0;
}

static void __exit stream_exit(void)
{
}
module_init(stream_init);
module_exit(stream_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Read-only A55 cache-control register diagnostic");
