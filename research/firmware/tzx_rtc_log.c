// SPDX-License-Identifier: GPL-2.0-only
/* Temporary reset breadcrumbs: GP1..3 retain data with the pinned TOC0.
 * GP0, boot/FEL diagnostics GP4..7, clock and fast-boot registers are untouched.
 */
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/kdebug.h>
#include <linux/kobject.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/panic_notifier.h>
#include <linux/reboot.h>
#include <linux/sysfs.h>
#include <asm/ptrace.h>

#define RTC_LOG_BASE 0x07090104
#define RTC_LOG_SIZE 12
#define SIGNATURE 0x54580000
#define ARMED 1
#define REBOOT 2
#define DIE 3
#define PANIC 4
#define DIE_PC_LR 5
#define STOPPED 6
static unsigned long long boot_cookie;
module_param(boot_cookie, ullong, 0400);
static void __iomem *gp;
static u32 previous[3];
static struct kobject *directory;
static atomic_t critical = ATOMIC_INIT(0);

static void record(unsigned int kind, u64 value)
{
    unsigned long flags;
    local_irq_save(flags);
    writel(0, gp);
    writel(lower_32_bits(value), gp + 4);
    writel(upper_32_bits(value), gp + 8);
    wmb();
    writel(SIGNATURE | ((raw_smp_processor_id() & 0xff) << 8) | kind, gp);
    wmb();
    readl(gp);
    local_irq_restore(flags);
}

static int on_die(struct notifier_block *nb, unsigned long event, void *data)
{
    struct die_args *args = data;
    if (event == DIE_OOPS && args && args->regs &&
        atomic_cmpxchg(&critical, 0, 1) == 0) {
        u64 pc = instruction_pointer(args->regs);
        u64 lr = args->regs->regs[30];
        /* This no-KASLR kernel and its modules share the fixed upper word.
         * Save both instruction and caller offsets when this is true;
         * otherwise keep the original full-width PC format.
         */
        if (upper_32_bits(pc) == 0xffff8000 && upper_32_bits(lr) == 0xffff8000)
            record(DIE_PC_LR, (u64)lower_32_bits(lr) << 32 | lower_32_bits(pc));
        else
            record(DIE, pc);
        pr_emerg("tzx-rtc-log: die pc=%px lr=%px x0=%016llx syndrome=%016lx\n",
                 (void *)pc, (void *)lr, args->regs->regs[0], args->err);
    }
    return NOTIFY_DONE;
}

static int on_panic(struct notifier_block *nb, unsigned long event, void *data)
{
    if (atomic_cmpxchg(&critical, 0, 1) == 0)
        record(PANIC, boot_cookie);
    return NOTIFY_DONE;
}

static int on_reboot(struct notifier_block *nb, unsigned long event, void *data)
{
    if (!atomic_read(&critical))
        record(REBOOT, boot_cookie);
    return NOTIFY_DONE;
}
static struct notifier_block die_nb = { .notifier_call = on_die, .priority = INT_MAX };
static struct notifier_block panic_nb = { .notifier_call = on_panic, .priority = INT_MAX };
static struct notifier_block reboot_nb = { .notifier_call = on_reboot, .priority = INT_MAX };

static ssize_t previous_read(struct file *file, struct kobject *kobj,
                             const struct bin_attribute *attr, char *buf,
                             loff_t off, size_t count)
{
    return memory_read_from_buffer(buf, count, &off, previous, sizeof(previous));
}
static const struct bin_attribute previous_file = {
    .attr = { .name = "previous", .mode = 0400 },
    .size = RTC_LOG_SIZE, .read = previous_read,
};

static int __init start(void)
{
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523") || !boot_cookie)
        return -ENODEV;
    /* The RTC driver owns the enclosing 1KiB register range. This fixed
     * kernel has RTC_NVMEM disabled, so its time/alarm operations never
     * access GP1..3. Keep its clock service bound and borrow only these
     * verified unused words; refuse kernels that expose writable GP nvmem.
     */
    if (IS_ENABLED(CONFIG_RTC_NVMEM))
        return -EBUSY;
    gp = ioremap(RTC_LOG_BASE, RTC_LOG_SIZE);
    if (!gp) {
        return -ENOMEM;
    }
    previous[0] = cpu_to_le32(readl(gp));
    previous[1] = cpu_to_le32(readl(gp + 4));
    previous[2] = cpu_to_le32(readl(gp + 8));
    directory = kobject_create_and_add("tzx_rtc_log", kernel_kobj);
    if (!directory) {
        ret = -ENOMEM;
        goto unmap;
    }
    ret = sysfs_create_bin_file(directory, &previous_file);
    if (ret)
        goto put;
    ret = register_die_notifier(&die_nb);
    if (ret)
        goto remove;
    ret = atomic_notifier_chain_register(&panic_notifier_list, &panic_nb);
    if (ret)
        goto unregister_die;
    ret = register_reboot_notifier(&reboot_nb);
    if (ret)
        goto unregister_panic;
    record(ARMED, boot_cookie);
    pr_info("tzx-rtc-log: reset breadcrumbs armed in GP1..3\n");
    return 0;
unregister_panic:
    atomic_notifier_chain_unregister(&panic_notifier_list, &panic_nb);
unregister_die:
    unregister_die_notifier(&die_nb);
remove:
    sysfs_remove_bin_file(directory, &previous_file);
put:
    kobject_put(directory);
unmap:
    iounmap(gp);
    return ret;
}

static void __exit stop(void)
{
    unregister_reboot_notifier(&reboot_nb);
    atomic_notifier_chain_unregister(&panic_notifier_list, &panic_nb);
    unregister_die_notifier(&die_nb);
    if (!atomic_read(&critical))
        record(STOPPED, boot_cookie);
    sysfs_remove_bin_file(directory, &previous_file);
    kobject_put(directory);
    iounmap(gp);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Temporary reset breadcrumbs for the pinned TZX A523 boot chain");
