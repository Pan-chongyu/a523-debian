// SPDX-License-Identifier: GPL-2.0-only
/* Temporary crash recorder for the pinned TZX boot chain. BL31 ends at
 * 0x5e000; its unused final 8 KiB stop before the SCP region at 0x60000.
 * A userspace guard verifies the exact installed BL31 before loading.
 */
#include <linux/crc32.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/kmsg_dump.h>
#include <linux/kobject.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/reboot.h>
#include <linux/slab.h>
#include <linux/sysfs.h>
#include <linux/timekeeping.h>
#include <linux/workqueue.h>

#define SRAM_BASE 0x5e000
#define SRAM_SIZE 8192
#define HEADER_SIZE 128
#define RECORD_SIZE (SRAM_SIZE / 2)
#define REASON_HEARTBEAT 0x100
#define REASON_REBOOT 0x101
static char *boot_id;
module_param(boot_id, charp, 0400);
static void __iomem *sram;
static unsigned char *previous, *scratch;
static struct kobject *directory;
static atomic_t writing[2] = { ATOMIC_INIT(0), ATOMIC_INIT(0) };
static bool stopping;
static atomic_t sequence = ATOMIC_INIT(0);
static struct delayed_work heartbeat;

struct log_header {
    u8 magic[8];
    __le32 version, reason, cpu, length;
    __le64 realtime_ns, monotonic_ns;
    __le32 crc, sequence;
    char boot_id[40];
    u8 padding[40];
} __packed;

static void save_record(unsigned int reason)
{
    struct kmsg_dump_iter iter;
    size_t length = 0;
    unsigned long flags;
    bool critical = reason <= KMSG_DUMP_OOPS;
    unsigned int bank = critical ? 1 : 0;
    unsigned char *buffer = scratch + bank * RECORD_SIZE;
    struct log_header *header = (void *)buffer;
    void __iomem *destination = sram + bank * RECORD_SIZE;

    /* Separate SRAM banks keep a panic on one CPU from racing the ordinary
     * delayed worker on another CPU. Nested critical dumps retain the first. */
    if (atomic_cmpxchg(&writing[bank], 0, 1))
        return;
    if (critical)
        WRITE_ONCE(stopping, true);
    local_irq_save(flags);
    memset(header, 0, HEADER_SIZE);
    memcpy(header->magic, "TZXLOG1", 7);
    kmsg_dump_rewind(&iter);
    kmsg_dump_get_buffer(&iter, true, buffer + HEADER_SIZE,
                         RECORD_SIZE - HEADER_SIZE, &length);
    header->version = cpu_to_le32(1);
    header->reason = cpu_to_le32(reason);
    header->cpu = cpu_to_le32(raw_smp_processor_id());
    header->length = cpu_to_le32(length);
    header->realtime_ns = cpu_to_le64(ktime_get_real_ns());
    header->monotonic_ns = cpu_to_le64(ktime_get_mono_fast_ns());
    header->crc = cpu_to_le32(crc32_le(~0U, buffer + HEADER_SIZE, length) ^ ~0U);
    header->sequence = cpu_to_le32(atomic_inc_return(&sequence));
    strscpy(header->boot_id, boot_id, sizeof(header->boot_id));
    /* Invalid signature until data and the other header fields reach SRAM. */
    writel(0, destination);
    memcpy_toio(destination + HEADER_SIZE, buffer + HEADER_SIZE, length);
    memcpy_toio(destination + 8, buffer + 8, HEADER_SIZE - 8);
    wmb();
    memcpy_toio(destination, buffer, 8);
    wmb();
    readl(destination);
    local_irq_restore(flags);
    atomic_set(&writing[bank], 0);
}

static void tick(struct work_struct *work)
{
    if (READ_ONCE(stopping))
        return;
    save_record(REASON_HEARTBEAT);
    if (!READ_ONCE(stopping))
        schedule_delayed_work(&heartbeat, 5 * HZ);
}

static void dump(struct kmsg_dumper *dumper, struct kmsg_dump_detail *detail)
{
    save_record(detail->reason);
}

static struct kmsg_dumper recorder = {
    .dump = dump,
    .max_reason = KMSG_DUMP_OOPS,
};

static int rebooting(struct notifier_block *nb, unsigned long event, void *unused)
{
    WRITE_ONCE(stopping, true);
    cancel_delayed_work_sync(&heartbeat);
    save_record(REASON_REBOOT);
    return NOTIFY_DONE;
}
static struct notifier_block reboot_notifier = { .notifier_call = rebooting };

static ssize_t previous_read(struct file *file, struct kobject *kobj,
                             const struct bin_attribute *attr, char *buf,
                             loff_t off, size_t count)
{
    return memory_read_from_buffer(buf, count, &off, previous, SRAM_SIZE);
}
static const struct bin_attribute previous_file = {
    .attr = { .name = "previous", .mode = 0400 },
    .size = SRAM_SIZE,
    .read = previous_read,
};

static int __init start(void)
{
    int ret;
    BUILD_BUG_ON(sizeof(struct log_header) != HEADER_SIZE);
    if (!of_machine_is_compatible("tzx,p30a523") || !boot_id || strlen(boot_id) != 36)
        return -ENODEV;
    if (!request_mem_region(SRAM_BASE, SRAM_SIZE, "tzx-sram-crash-log"))
        return -EBUSY;
    sram = ioremap(SRAM_BASE, SRAM_SIZE);
    previous = kmalloc(SRAM_SIZE, GFP_KERNEL);
    scratch = kzalloc(SRAM_SIZE, GFP_KERNEL);
    ret = -ENOMEM;
    if (!sram || !previous || !scratch)
        goto free;
    memcpy_fromio(previous, sram, SRAM_SIZE);
    directory = kobject_create_and_add("tzx_sram_log", kernel_kobj);
    if (!directory)
        goto free;
    ret = sysfs_create_bin_file(directory, &previous_file);
    if (ret)
        goto put;
    INIT_DELAYED_WORK(&heartbeat, tick);
    ret = kmsg_dump_register(&recorder);
    if (ret)
        goto remove;
    ret = register_reboot_notifier(&reboot_notifier);
    if (ret)
        goto unregister;
    schedule_delayed_work(&heartbeat, 5 * HZ);
    pr_info("tzx-sram-log: temporary 8KiB recorder at 0x5e000; no boot payload writes\n");
    return 0;
unregister:
    kmsg_dump_unregister(&recorder);
remove:
    sysfs_remove_bin_file(directory, &previous_file);
put:
    kobject_put(directory);
free:
    kfree(scratch);
    kfree(previous);
    if (sram)
        iounmap(sram);
    release_mem_region(SRAM_BASE, SRAM_SIZE);
    return ret;
}

static void __exit stop(void)
{
    WRITE_ONCE(stopping, true);
    cancel_delayed_work_sync(&heartbeat);
    unregister_reboot_notifier(&reboot_notifier);
    kmsg_dump_unregister(&recorder);
    sysfs_remove_bin_file(directory, &previous_file);
    kobject_put(directory);
    kfree(scratch);
    kfree(previous);
    iounmap(sram);
    release_mem_region(SRAM_BASE, SRAM_SIZE);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Temporary TZX A523 pinned-boot-chain SRAM crash capture");
