/* SPDX-License-Identifier: MIT */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define HEADER ((uint32_t *)0x30000)
extern int cold_emmc_init(void);
extern int cold_emmc_read(unsigned, void *);
extern void enter_arm64(unsigned address);

/* Keep the failing stage/sector across reset and return through the existing
 * one-shot FEL guard. Returning normally disables the watchdog in the DRAM
 * caller and can leave the host without a recoverable USB device. */
static __attribute__((noreturn)) void chain_fail(unsigned stage, unsigned detail) {
    REG(0x07090110) = stage;
    REG(0x07090114) = detail;
    REG(0x0709011c) = REG(0x04022038);
    REG(0x07090118) = 0xa52322ee;
    __asm__ volatile("dsb sy" ::: "memory");
    REG(0x02050008) = 0x16aa0001;
    __asm__ volatile("dsb sy" ::: "memory");
    for (;;) __asm__ volatile("wfi");
}

static uint32_t crc_table[256];
static void crc32_init(void) {
    for (unsigned n = 0; n < 256; n++) {
        uint32_t value = n;
        for (unsigned bit = 0; bit < 8; bit++)
            value = (value >> 1) ^ (0xedb88320 & -(value & 1));
        crc_table[n] = value;
    }
}

static uint32_t crc32_update(uint32_t crc, const void *data, unsigned length) {
    const unsigned char *p = data;
    while (length--) {
        crc = (crc >> 8) ^ crc_table[(crc ^ *p++) & 255];
    }
    return crc;
}

void chain_load(void) {
    /* The SRAM loader cannot rely on the boot ROM's watchdog clock state.
     * Bound PIO polling remains in place; re-arm the boot watchdog once the
     * complete, verified payload is ready for the ARM64 hand-off. */
    REG(0x0205000c) = 0x14af;
    REG(0x02050014) = 0x16aa0000;
    __asm__ volatile("dsb sy" ::: "memory");
    crc32_init();
    REG(0x07090110) = 0xa5234401;
    if (cold_emmc_init()) chain_fail(0xa52344e0, 0);
    if (cold_emmc_read(4096, HEADER)) chain_fail(0xa52344e1, 4096);
    if (HEADER[0] != 0x33323541 || HEADER[1] != 0x31444e42 || HEADER[2] != 1 || HEADER[3] != 5)
        chain_fail(0xa52344e2, HEADER[0]);
    uint32_t header_crc = HEADER[4];
    HEADER[4] = 0;
    if (~crc32_update(0xffffffff, HEADER, 512) != header_crc) chain_fail(0xa52344e3, header_crc);
    for (unsigned i = 0; i < 5; i++) {
        const uint32_t *item = HEADER + 8 + i * 6;
        unsigned lba = item[0], bytes = item[1], address = item[2], expected_crc = item[3];
        unsigned rounded = (bytes + 511) & -512U;
        static const unsigned targets[] = {0x48080000, 0x47000000, 0x60000000, 0x4a000000, 0x54000};
        static const unsigned maximum[] = {0x1f80000, 0x100000, 0x1000000, 0x100000, 0xc000};
        if (address != targets[i] || !bytes || rounded > maximum[i] || lba < 4097 || lba + rounded / 512 > 131072)
            chain_fail(0xa52344e4, i);
        REG(0x07090110) = 0xa5234410 + i;
        uint32_t actual_crc = 0xffffffff;
        for (unsigned offset = 0; offset < rounded; offset += 512) {
            uint32_t *staging = (uint32_t *)0x30200;
            volatile uint32_t *dest = (volatile uint32_t *)(address + offset);
            REG(0x07090114) = lba + offset / 512;
            if (!(offset & 0x7fff)) {
                uint64_t ticks;
                __asm__ volatile("mrrc p15, 0, %Q0, %R0, c14" : "=r"(ticks));
                REG(0x07090108) = (uint32_t)ticks;
                REG(0x0709010c) = (uint32_t)(ticks >> 32);
            }
            REG(0x07090100) = 0xa5234510;
            __asm__ volatile("dsb sy" ::: "memory");
            if (cold_emmc_read(lba + offset / 512, staging))
                chain_fail(0xa52344f0 + i, lba + offset / 512);
            REG(0x07090100) = 0xa5234520;
            __asm__ volatile("dsb sy" ::: "memory");
            for (unsigned word = 0; word < 128; word++) dest[word] = staging[word];
            __asm__ volatile("dsb sy" ::: "memory");
            REG(0x07090100) = 0xa5234530;
            __asm__ volatile("dsb sy" ::: "memory");
            for (unsigned word = 0; word < 128; word++)
                if (dest[word] != staging[word]) chain_fail(0xa52344d0 + i, lba + offset / 512);
            REG(0x07090100) = 0xa5234540;
            __asm__ volatile("dsb sy" ::: "memory");
            /* DRAM was compared above with aligned word reads. Calculate the
             * transport checksum from the identical SRAM staging block. */
            actual_crc = crc32_update(actual_crc, staging, 512);
            REG(0x0205000c) = 0x14af;
            __asm__ volatile("dsb sy" ::: "memory");
        }
        if (~actual_crc != expected_crc) {
            chain_fail(0xa52344c0 + i, actual_crc);
        }
        REG(0x0205000c) = 0x14af;
    }
    /* TF-A registers UART0 even without a connected debug cable. Enable its
     * clock/reset so its final transmitter-empty check can complete. */
    REG(0x0200190c) |= (1U << 16) | 1;
    REG(0x02000034) = (REG(0x02000034) & ~0xff0U) | 0x220;
    REG(0x07090110) = 0xa5234404;
    REG(0x0205000c) = 0x14af;
    REG(0x02050010) = 0x16aa0001;
    REG(0x02050014) = 0x16aa00b1;
    __asm__ volatile("dsb sy; isb" ::: "memory");
    enter_arm64(0x54000);
}
