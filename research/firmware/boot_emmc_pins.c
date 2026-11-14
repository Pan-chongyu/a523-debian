/* SPDX-License-Identifier: MIT
 * Volatile legacy-SDR bus-width change only. Linux already qualifies all
 * eight physical data lines at HS200/100MHz. Preserve the boot clock and
 * validate three distinct sectors against the 1-bit reader before use.
 * No user/boot sector, timing mode, clock or voltage is written here.
 */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define RECEIPT ((volatile uint32_t *)0x2df80)
extern void udelay(unsigned);

int boot_emmc_pins(void)
{
    int (*init)(void) = (int (*)(void))0x4c500;
    int (*read_sector)(unsigned, uint32_t *) = (int (*)(unsigned, uint32_t *))0x44bac;
    int (*command)(unsigned,unsigned,unsigned,unsigned *) =
        (int (*)(unsigned,unsigned,unsigned,unsigned *))0x446cc;
    int result = init();
    if (result) return result;
    RECEIPT[0] = 0xa523b801;
    RECEIPT[1] = 0;
    RECEIPT[2] = REG(0x0402200c);
    RECEIPT[3] = REG(0x04022004);
    RECEIPT[4] = 0;
    RECEIPT[5] = 0;
    RECEIPT[6] = 0;
    RECEIPT[7] = REG(0x02001838);
    if (RECEIPT[2] != 0 || RECEIPT[3] != 0x10000) {
        RECEIPT[1] = 3;
        return 0;
    }
    /* The qualified Linux DT uses PC11/13/14/15/16 in addition to the
     * old helper's PC0..10. Preserve PC12 and unrelated functions. */
    volatile uint32_t *pins = (volatile uint32_t *)0x2dfa0;
    pins[0]=REG(0x02000060); pins[1]=REG(0x02000064); pins[2]=REG(0x02000068);
    REG(0x02000064)=(pins[1]&~0xfff0f000U)|0x33303000;
    REG(0x02000068)=(pins[2]&~0xfU)|3;
    __asm__ volatile("dsb sy" ::: "memory");
    const unsigned sectors[] = {4096, 98305, 100353};
    uint32_t *baseline = (uint32_t *)0x30400;
    uint32_t *trial = (uint32_t *)0x30a00;
    for (unsigned n=0; n<3; n++) {
        result = read_sector(sectors[n], baseline+n*128);
        if (result) { RECEIPT[1]=5; return result; }
    }
    unsigned response = 0;
    result = command(6, 0x03b70200, (1U<<8)|(1U<<6), 0);
    if (result) goto fallback;
    unsigned n;
    for (n=0; n<4000; n++) {
        if (!(REG(0x0402203c)&(1U<<9))) break;
        udelay(50);
    }
    if (n==4000) { RECEIPT[6]=1; goto fallback; }
    udelay(1000);
    result = command(13, 1U<<16, (1U<<8)|(1U<<6), &response);
    if (result || (response&(1U<<7))) { RECEIPT[6]=2; goto fallback; }
    REG(0x0402200c) = 2;
    __asm__ volatile("dsb sy" ::: "memory");
    for (n=0; n<3; n++) {
        result = read_sector(sectors[n], trial);
        if (result) { RECEIPT[6]=3; goto fallback; }
        for (unsigned word=0; word<128; word++)
            if (trial[word] != baseline[n*128+word]) { RECEIPT[6]=4+n; goto fallback; }
        RECEIPT[4] = n+1;
    }
    RECEIPT[1] = 1;
    RECEIPT[5] = REG(0x0402200c);
    __asm__ volatile("dsb sy" ::: "memory");
    return 0;
fallback:
    // Reset the card and controller through the unchanged known-good init.
    REG(0x02000064)=pins[1]; REG(0x02000068)=pins[2];
    __asm__ volatile("dsb sy" ::: "memory");
    result = init();
    RECEIPT[1] = 4;
    RECEIPT[5] = REG(0x0402200c);
    __asm__ volatile("dsb sy" ::: "memory");
    return result;
}
