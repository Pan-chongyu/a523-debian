/* SPDX-License-Identifier: MIT
 * Runs from SRAM before DRAM training. Uses the sunxi TWI protocol documented
 * in SyterKit's i2c driver. Only PMIC register 0x85 may be written.
 */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define TWI 0x07081400
#define RECEIPT ((volatile uint32_t *)0x2e080)
extern void udelay(unsigned);
extern int printf_dram(const char *, ...);

static int wait_status(unsigned expected)
{
    for (unsigned i = 0; i < 2000; i++) {
        if (REG(TWI+0x0c) & 8) return REG(TWI+0x10) == expected ? 0 : -1;
        udelay(5);
    }
    return -1;
}

static int start(unsigned expected)
{
    REG(TWI+0x0c) = 0x68;
    return wait_status(expected);
}

static int send(unsigned byte, unsigned expected)
{
    REG(TWI+0x08) = byte;
    REG(TWI+0x0c) = 0x48;
    return wait_status(expected);
}

static void stop(void)
{
    REG(TWI+0x0c) = 0x58;
    for (unsigned i = 0; i < 2000; i++) {
        if (!(REG(TWI+0x0c) & 0x10)) break;
        udelay(5);
    }
}

static int read_register(unsigned address, unsigned reg)
{
    int value = -1;
    if (start(8) || send(address << 1, 0x18) || send(reg, 0x28) ||
        start(0x10) || send((address << 1)|1, 0x40)) goto out;
    REG(TWI+0x0c) = 0x48; /* final byte NACK */
    if (!wait_status(0x58)) value = REG(TWI+0x08) & 0xff;
out:
    stop();
    return value;
}

static int write_dcdc3(unsigned value)
{
    if (value < 0xbc || value > 0xc9) return -1;
    int failed = start(8) || send(0x68, 0x18) || send(0x85, 0x28) || send(value, 0x28);
    stop();
    return failed ? -1 : 0;
}

int dram_boot_voltage_hook(unsigned millivolts)
{
    RECEIPT[0] = 0xa523dc03;
    RECEIPT[1] = millivolts;
    RECEIPT[2] = 0xffffffff;
    RECEIPT[3] = 0xffffffff;
    RECEIPT[4] = 1;
    if (millivolts != 1260) return -1;
    /* R_TWI0 clock/reset and PL0/PL1 mux. Retain all unrelated fields. */
    REG(0x0701019c) |= 0x10001;
    udelay(100);
    REG(0x07022000) = (REG(0x07022000) & ~0xffU) | 0x22;
    REG(0x07022024) = (REG(0x07022024) & ~0xfU) | 5;
    REG(TWI+0x18) = 1;
    for (unsigned i = 0; REG(TWI+0x18) & 1; i++) {
        if (i == 2000) goto failure;
        udelay(5);
    }
    REG(TWI+0x1c) = 0;
    REG(TWI+0x14) = 0x59; /* 24MHz/(10*12*2), 100kHz */
    REG(TWI+0x0c) = 0x40;
    udelay(100);
    if (read_register(0x36, 3) != 0x49 || read_register(0x34, 0x80) != 0x0f ||
        read_register(0x34, 0x83) != 0xa8 || read_register(0x34, 0x84) != 0xa8 ||
        read_register(0x34, 0x86) != 0 || read_register(0x34, 0x98) != 0x0d) goto failure;
    int original = read_register(0x34, 0x85);
    RECEIPT[2] = original;
    if (original < 0xbc || original > 0xc9) goto failure;
    for (unsigned value = original+1; value <= 0xc9; value++) {
        RECEIPT[4] = 0x100 | value;
        if (write_dcdc3(value)) goto failure;
        udelay(1000);
        int actual = read_register(0x34, 0x85);
        RECEIPT[3] = actual;
        if (actual != (int)value) goto failure;
    }
    RECEIPT[3] = read_register(0x34, 0x85);
    if (RECEIPT[3] != 0xc9) goto failure;
    __asm__ volatile("dsb sy" ::: "memory");
    RECEIPT[4] = 2;
    printf_dram("AXP717 DCDC3 requested=%u actual-reg=%x before-training\n", millivolts, RECEIPT[3]);
    return 0;
failure:
    RECEIPT[4] = 0xee;
    __asm__ volatile("dsb sy" ::: "memory");
    printf_dram("AXP717 DCDC3 hook failed stage=%x\n", RECEIPT[4]);
    return -1;
}
