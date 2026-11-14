/* SPDX-License-Identifier: MIT
 * Minimal board DRAM caller using a freshly downloaded SyterKit DRAM library.
 * It leaves voltage selection to the board's existing PMIC settings.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>

#define RECEIPT ((volatile uint32_t *)0x0002e000)
#define LOG ((volatile char *)0x0002e100)
#define INPUT ((uint32_t *)0x0002f000)
#define REG(a) (*(volatile uint32_t *)(a))
#ifdef COLD_BOOT
#include "dram_params.h"
#undef INPUT
#define INPUT board_dram_parameters
#endif
static unsigned log_offset;
extern int init_DRAM(int type, void *parameters);
#ifdef CHAIN_BOOT
extern void chain_load(void);
#endif

void *memset(void *dest, int value, size_t count) {
    unsigned char *p = dest;
    while (count--) *p++ = value;
    return dest;
}
static uint64_t counter(void) {
    uint64_t value;
    __asm__ volatile("mrrc p15, 0, %Q0, %R0, c14" : "=r"(value));
    return value;
}
void udelay(unsigned us) {
    uint64_t start = counter();
    while (counter() - start < (uint64_t)us * 24) {}
}
int set_ddr_voltage(unsigned value) { (void)value; return 0; }
static void put(char c) { if (log_offset < 3500) LOG[log_offset++] = c; LOG[log_offset] = 0; }
static void number(unsigned n, unsigned base) {
    char buffer[16]; unsigned i = 0;
    do { buffer[i++] = "0123456789abcdef"[n % base]; n /= base; } while(n);
    while (i) put(buffer[--i]);
}
int printf_dram(const char *format, ...) {
    va_list ap; va_start(ap, format);
    while (*format) {
        if (*format != '%') { put(*format++); continue; }
        format++;
        while ((*format >= '0' && *format <= '9') || *format == 'l' || *format == '-') format++;
        char spec = *format ? *format++ : 0;
        if (spec == 's') { const char *s = va_arg(ap, const char *); if (s) while (*s) put(*s++); }
        else if (spec == 'x' || spec == 'X' || spec == 'p') number(va_arg(ap, unsigned), 16);
        else if (spec == 'd' || spec == 'u') number(va_arg(ap, unsigned), 10);
        else if (spec == 'c') put(va_arg(ap, int));
        else if (spec) put(spec);
    }
    va_end(ap); return 0;
}
void dram_probe(void) {
#ifdef COLD_BOOT
    /* A523 watchdog layout from upstream sunxi_wdt.c and sun55i-a523.dtsi.
     * A timed-out attempt returns to FEL on its next boot instead of looping.
     */
    REG(0x02050014) = 0x16aa0000;
    if (REG(0x07090118) == 0xa52322ee) {
        REG(0x07090118) = 0;
        return;
    }
    REG(0x07090118) = 0xa52322ee;
    REG(0x07090110) = 0xa5232201;
    REG(0x02050010) = 0x16aa0001;
    REG(0x02050014) = 0x16aa00b1;
    REG(0x0205000c) = 0x14af;
#endif
    uint32_t cpsr;
    __asm__ volatile("mrs %0, cpsr" : "=r"(cpsr));
    RECEIPT[0] = 0x4452414d;
    RECEIPT[1] = 1;
    RECEIPT[2] = cpsr;
    uint32_t sctlr;
    __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(sctlr));
    RECEIPT[8] = sctlr;
    log_offset = 0;
    LOG[0] = 0;
    __asm__ volatile("dsb sy" ::: "memory");
    int size = init_DRAM(0, INPUT);
    RECEIPT[3] = size;
    RECEIPT[4] = INPUT[7];
    RECEIPT[1] = 2;
    __asm__ volatile("dsb sy" ::: "memory");
#ifdef COLD_BOOT
    REG(0x07090110) = 0xa5232202;
    REG(0x07090114) = size;
    if (size > 0) {
        volatile uint32_t *p = (volatile uint32_t *)0x41000000;
        unsigned errors = 0;
        for (unsigned i = 0; i < 8192; i++) p[i] = 0xa5c30000 ^ (i * 0x10001);
        __asm__ volatile("dsb sy" ::: "memory");
        for (unsigned i = 0; i < 8192; i++) {
            if (p[i] != (0xa5c30000 ^ (i * 0x10001))) {
                if (!errors) { RECEIPT[6] = i; RECEIPT[7] = p[i]; }
                errors++;
            }
        }
        RECEIPT[5] = errors;
        REG(0x07090110) = errors ? 0xa52322ff : 0xa5232203;
#ifdef CHAIN_BOOT
        if (!errors) chain_load();
#endif
    }
    REG(0x02050014) = 0x16aa0000;
    REG(0x07090118) = 0;
#endif
}
