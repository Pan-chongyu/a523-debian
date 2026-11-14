/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Two permanent DMA32 buffers. RCQ owns the register latch at frame boundary;
 * only the buffer not currently fetched by DE is filled by the CPU.
 */
static unsigned int screen_front_buffer;
static unsigned long screen_buffer_commits, screen_buffer_errors;
static unsigned long screen_front_dma;
static bool screen_buffer_frozen;
module_param(screen_buffer_commits, ulong, 0444);
module_param(screen_buffer_errors, ulong, 0444);
module_param(screen_front_dma, ulong, 0444);

static void *screen_back_buffer(void)
{
    dma_addr_t expected = screen_front_buffer ? screen_second_dma : fb_dma;
    if (screen_buffer_frozen) return NULL;
    if (readl(de + OVL + 0x10) != lower_32_bits(expected) ||
        readl(de + OVL + 0x80) != upper_32_bits(expected)) {
        screen_buffer_errors++;
        screen_buffer_frozen = true;
        drm_err(&display->drm, "unexpected active scanout address; updates frozen\n");
        return NULL;
    }
    return screen_front_buffer ? fb : screen_second;
}

static int screen_commit_back_buffer(void)
{
    struct rcq_head *heads = regs;
    unsigned int next = screen_front_buffer ^ 1;
    dma_addr_t address = next ? screen_second_dma : fb_dma;
    unsigned long flags;
    u32 status;
    int ret;

    /* The preceding transaction has finished before its memory is reused. */
    writel(0, de + 0x8110);
    readl(de + 0x8110);
    for (unsigned int i = 0; i < ARRAY_SIZE(blocks); i++)
        heads[i].dirty = 0;
    swrite(0, 0x10, lower_32_bits(address));
    swrite(1, 0, upper_32_bits(address));
    heads[0].dirty = cpu_to_le32(1);
    heads[1].dirty = cpu_to_le32(1);
    dma_wmb();

    /* The A523 BSP arms RCQ while DE is busy, outside the blank interval. */
    ret = -ETIMEDOUT;
    for (unsigned int attempt = 0; attempt < 1000; attempt++) {
        local_irq_save(flags);
        status = readl(de + 0x8104);
        if (status & BIT(4)) {
            writel(BIT(2) | BIT(3), de + 0x8104); /* FINISH/ACCEPT W1C */
            writel(1, de + 0x8110);
            local_irq_restore(flags);
            ret = 0;
            break;
        }
        local_irq_restore(flags);
        usleep_range(20, 40);
    }
    if (!ret)
        ret = readl_poll_timeout(de + 0x8104, status, status & BIT(2), 50, 60000);
    if (!ret && (readl(de + OVL + 0x10) != lower_32_bits(address) ||
                 readl(de + OVL + 0x80) != upper_32_bits(address)))
        ret = -EIO;
    if (ret) {
        screen_buffer_errors++;
        screen_buffer_frozen = true;
        drm_err(&display->drm, "RCQ buffer update failed %d; updates frozen\n", ret);
        return ret;
    }
    writel(0, de + 0x8110);
    screen_front_buffer = next;
    screen_front_dma = address;
    screen_buffer_commits++;
    return 0;
}
