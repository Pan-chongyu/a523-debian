/* SPDX-License-Identifier: MIT
 * Bring up the same already-qualified 480MHz CPU4-7 clock after DRAM and
 * exact eMMC identity validation, before Linux starts secondary CPUs.
 * This is the sequence in enable_cpub.c; no PMIC or voltage is touched.
 */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define RECEIPT ((volatile uint32_t *)0x2df40)
extern void udelay(unsigned);

int boot_cpub_early(void)
{
    int result = ((int (*)(void))0x44c7c)();
    if (result)
        return result;
    uint32_t pll = REG(0x0881700c), mux = REG(0x08817064);
    RECEIPT[0] = 0xa523cb01;
    RECEIPT[1] = 0;
    RECEIPT[2] = pll;
    RECEIPT[3] = mux;
    if ((mux & (3U << 24)) == (3U << 24)) {
        RECEIPT[1] = 2;
        goto out;
    }
    if ((mux & (3U << 24)) != 0 || pll != 0x48801400) {
        RECEIPT[1] = 3;
        goto out;
    }
    REG(0x0881700c) = 0xe4801400;
    __asm__ volatile("dsb sy" ::: "memory");
    unsigned n;
    for (n = 0; n < 1000; n++) {
        if (REG(0x0881700c) & (1U << 28))
            break;
        udelay(100);
    }
    if (n == 1000) {
        REG(0x0881700c) = pll;
        RECEIPT[1] = 4;
        goto out;
    }
    udelay(20);
    REG(0x0881700c) = (REG(0x0881700c) | (1U << 27) | (1U << 26)) & ~(1U << 29);
    __asm__ volatile("dsb sy" ::: "memory");
    udelay(20);
    REG(0x08817064) = (mux & ~((3U << 24) | (1U << 16))) | (3U << 24);
    __asm__ volatile("dsb sy; isb" ::: "memory");
    RECEIPT[1] = 1;
out:
    RECEIPT[4] = REG(0x0881700c);
    RECEIPT[5] = REG(0x08817064);
    __asm__ volatile("dsb sy" ::: "memory");
    return result;
}
