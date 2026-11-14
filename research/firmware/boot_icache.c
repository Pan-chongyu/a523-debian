/* SPDX-License-Identifier: MIT
 * Enable only the instruction cache after the exact-CID initialization.
 * MMU/data cache are never enabled. Restore SCTLR before the ARM64 handoff.
 */
#include <stdint.h>
#define RECEIPT ((volatile uint32_t *)0x2dfc0)
static uint32_t read_control(void) {
    uint32_t value;
    __asm__ volatile("mrc p15, 0, %0, c1, c0, 0":"=r"(value));
    return value;
}
static void invalidate(void) {
    uint32_t zero=0;
    __asm__ volatile("mcr p15, 0, %0, c7, c5, 0\n"
        "mcr p15, 0, %0, c7, c5, 6\n"
        "dsb sy\nisb"::"r"(zero):"memory");
}
static void write_control(uint32_t value) {
    __asm__ volatile("dsb sy\nmcr p15, 0, %0, c1, c0, 0\nisb"::"r"(value):"memory");
}
int boot_icache_init(void) {
    int result=((int (*)(void))0x4c700)();
    if (result)return result;
    uint32_t original=read_control();
    RECEIPT[0]=0xa5231c01;RECEIPT[1]=0;RECEIPT[2]=original;RECEIPT[3]=original;
    RECEIPT[4]=0;RECEIPT[5]=0;
    if (original&5) {RECEIPT[1]=3;return 0;}
    if (original&(1U<<12)) {RECEIPT[1]=2;return 0;}
    invalidate();
    write_control(original|(1U<<12));
    RECEIPT[3]=read_control();RECEIPT[1]=1;
    __asm__ volatile("dsb sy":::"memory");
    return 0;
}
void boot_icache_restore(void) {
    if (RECEIPT[0]==0xa5231c01 && RECEIPT[1]==1) {
        write_control(RECEIPT[2]);
        invalidate();
        RECEIPT[1]=4;
    }
    RECEIPT[4]=read_control();
}
__attribute__((noreturn)) void boot_icache_handoff(unsigned address) {
    boot_icache_restore();
    RECEIPT[5]=address;
    __asm__ volatile("dsb sy\nisb":::"memory");
    ((void (*)(unsigned))0x4403c)(address);
    for (;;) __asm__ volatile("wfi");
}
/* The frozen chain_load's common failure exit pops r4-r11 and PC after
 * dropping its locals. Preserve its return value and exact original stack. */
__attribute__((naked)) void boot_icache_failure(void) {
    __asm__ volatile("push {r0-r3,r12,lr}\nsub sp,sp,#4\n"
        "bl boot_icache_restore\nadd sp,sp,#4\npop {r0-r3,r12,lr}\n"
        "pop {r4-r11,pc}");
}
