/* SPDX-License-Identifier: MIT */
#include "compact_lz4.h"
#include "compact_config.h"
struct receipt {
    uint32_t magic, version, phase;
    int32_t error;
    uint32_t raw, packed, esr, crc;
    uint64_t entered, relocated, decoded, checked;
    uint32_t hz, reserved;
    uint64_t exception_pc;
};
#define R ((volatile struct receipt *)0x2d800)
extern void compact_cache_enable(void);
static uint64_t ticks(void) { uint64_t n; __asm__ volatile("mrs %0, cntpct_el0":"=r"(n)); return n; }
int compact_boot(void)
{
    volatile uint32_t *words = (volatile uint32_t *)R;
    for (unsigned i=0; i<sizeof(*R)/4; ++i) words[i]=0;
    R->magic=0xa523c701; R->version=1; R->phase=1; R->entered=ticks();
    uint64_t hz, features;
    __asm__ volatile("mrs %0, cntfrq_el0":"=r"(hz)); R->hz=hz;
    __asm__ volatile("mrs %0, id_aa64isar0_el1":"=r"(features));
    if (!((features>>16)&15)) { R->error=1; return 1; }
    uint64_t hcr;
    __asm__ volatile("mrs %0, hcr_el2":"=r"(hcr));
    if (hcr & (1ULL<<34)) { R->error=5; return 5; }
    const uint32_t *h=(const uint32_t *)0x48080000;
    if (h[0]!=0x33323541 || h[1]!=0x00345a4c || h[2]!=1 ||
        h[3]!=COMPACT_RAW || h[4]!=COMPACT_PACKED || h[5]!=COMPACT_CRC || h[6] || h[7]) {
        R->error=2; return 2;
    }
    R->raw=h[3]; R->packed=h[4];
    /* 39-bit VA, 4-KiB L1 root: only the low device block and the 1-GiB
     * identity RAM block used by this entry. All other addresses fault.
     * No device is mapped as cacheable Normal memory.
     */
    volatile uint64_t *table=(volatile uint64_t *)0x4bf00000;
    unsigned i;
    for (i=0; i<512; ++i) table[i]=0;
    table[0]=(1ULL<<54)|0x401; /* Device-nGnRnE, execute-never, AF. */
    table[1]=0x40000705;      /* Normal WBWA, inner-shareable, AF. */
    __asm__ volatile("dsb sy":::"memory");
    compact_cache_enable();
    R->reserved=1;
    const uint64_t *src=(const uint64_t *)0x48080020;
    uint64_t *relocated=(uint64_t *)0x50000000;
    for (i=0; i<COMPACT_PACKED/8; ++i) relocated[i]=src[i];
    for (i*=8; i<COMPACT_PACKED; ++i) ((uint8_t *)relocated)[i]=((const uint8_t *)src)[i];
    __asm__ volatile("dsb sy":::"memory");
    R->phase=2; R->relocated=ticks();
    int result=compact_lz4((const uint8_t *)relocated, COMPACT_PACKED, (uint8_t *)0x48000000, COMPACT_RAW);
    if (result) { R->error=result; return result; }
    R->phase=3; R->decoded=ticks();
    const uint64_t *image=(const uint64_t *)0x48000000;
    if (image[1] || image[2]<COMPACT_RAW || image[2]>0x1f80000 || (image[2]&15) ||
        *(const uint32_t *)0x48000038!=0x644d5241) { R->error=3; return 3; }
    R->crc=compact_crc32((const void *)image, COMPACT_RAW);
    if (R->crc!=COMPACT_CRC) { R->error=4; return 4; }
    R->phase=4; R->checked=ticks();
    return 0;
}
