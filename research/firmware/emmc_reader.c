/* SPDX-License-Identifier: MIT
 * Reuse the freshly built upstream PIO reader. Unused write/EXT_CSD paths
 * are removed by --gc-sections and are never called by the cold loader.
 */
#define main unused_fel_entry
#define work unused_fel_work
#include "../upstream/A523-root/tools/fel-emmc.c"

int cold_emmc_init(void) {
    unsigned cid[4];
    int result = emmc_init(cid);
    if (result) return result;
    /* The response-word order is the same as the freshly verified helper. */
    const unsigned expected[4] = {0x70281b59, 0x20102091, 0x454d2020, 0x3e01ff55};
    for (unsigned i = 0; i < 4; i++) {
        ((volatile unsigned *)0x2df00)[i] = cid[i];
        if (cid[i] != expected[i]) return -9;
    }
    return 0;
}

int cold_emmc_read(unsigned sector, void *data) {
    /* Follow the FIFO availability protocol used by U-Boot and SyterKit.
     * DATA_OVER alone does not authorize 128 unconditional bus reads.
     * A read from an empty FIFO can stall the CPU before a software timeout
     * or exception handler can run. Never consume more than its reported
     * level, and check the command/data completion after draining it. */
    unsigned *out = data, words = 0, polls = 0;
    const unsigned fatal = RINT_ERR_MASK & ~RINT_END_ERR;
    setbits(SMHC_GCTRL, BIT(31) | BIT(1));
    for (unsigned n = 0; readl(SMHC_GCTRL) & BIT(1); n++)
        if (n == 100000) return -10;
    setbits(SMHC_GCTRL, BIT(31));
    writel(0xffffffff, SMHC_RINT);
    dsb();
    writel(512, SMHC_BLKSIZ);
    writel(512, SMHC_BYTCNT);
    writel(sector, SMHC_CMDARG);
    writel(BIT(31) | BIT(13) | BIT(9) | BIT(8) | BIT(6) | 17,
           SMHC_CMD);
    dsb();
    while (words < 128) {
        unsigned ri = readl(SMHC_RINT);
        unsigned status = readl(SMHC_STATUS);
        writel(words, RTC_GP(1));
        writel(ri, RTC_GP(7));
        if (ri & fatal) return -11;
        if (status & BIT(2)) {
            if (++polls == 2000000) return -12;
            continue;
        }
        unsigned available = (status >> 17) & 0x3fff;
        if (!available && (status & BIT(3))) available = 32;
        if (!available) {
            if (++polls == 2000000) return -13;
            continue;
        }
        if (available > 128 - words) available = 128 - words;
        dsb();
        for (unsigned n = 0; n < available; n++)
            out[words++] = *(volatile unsigned *)SMHC_FIFO;
        dmb();
        polls = 0;
    }
    for (unsigned n = 0; n < 2000000; n++) {
        unsigned ri = readl(SMHC_RINT);
        if (ri & fatal) return -14;
        if ((ri & (RINT_CMD_DONE | RINT_DATA_OVER)) ==
            (RINT_CMD_DONE | RINT_DATA_OVER)) {
            writel(0xffffffff, SMHC_RINT);
            dsb();
            return 0;
        }
    }
    return -15;
}
