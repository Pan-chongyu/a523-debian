/* SPDX-License-Identifier: MIT
 * Read-only counters around the already-qualified loader routines.
 * The original routines still own all hardware and payload validation.
 */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
struct profile {
    uint32_t magic, version;
    uint64_t start, init_end, read_ticks, crc_ticks, last;
    uint32_t reads, crcs, cpua_pll, cpua_mux, mmc_clock, mmc_width, counter_hz;
    int32_t last_read_error;
};
#define P ((volatile struct profile *)0x2dc00)
static inline uint64_t ticks(void) {
    uint64_t value;
    __asm__ volatile("mrrc p15, 0, %Q0, %R0, c14" : "=r"(value));
    return value;
}
int boot_profile_init(void) {
    volatile uint32_t *p = (volatile uint32_t *)P;
    for (unsigned i=0; i<sizeof(*P)/4; i++) p[i]=0;
    P->magic=0xa523f101; P->version=1;
    P->start=ticks();
    P->cpua_pll=REG(0x08817004); P->cpua_mux=REG(0x08817060);
    uint32_t hz;
    __asm__ volatile("mrc p15, 0, %0, c14, c0, 0" : "=r"(hz));
    P->counter_hz=hz;
    int result=((int (*)(void))0x4c300)();
    P->init_end=ticks();
    P->mmc_clock=REG(0x02001838); P->mmc_width=REG(0x0402200c);
    return result;
}
int boot_profile_read(unsigned lba, void *data) {
    uint64_t before=ticks();
    int result=((int (*)(unsigned,void *))0x44bac)(lba,data);
    uint64_t after=ticks();
    P->read_ticks+=after-before; P->last=after;
    P->reads++; P->last_read_error=result;
    return result;
}
uint32_t boot_profile_crc(uint32_t crc, const void *data) {
    uint64_t before=ticks();
    uint32_t result=((uint32_t (*)(uint32_t,const void *))0x4be00)(crc,data);
    uint64_t after=ticks();
    P->crc_ticks+=after-before; P->last=after; P->crcs++;
    return result;
}
