/* SPDX-License-Identifier: MIT
 * A55's IEEE CRC32W uses the same reflected polynomial as the boot header.
 * Check the AArch32 feature register; retain the exact software fallback.
 */
#include <arm_acle.h>
#include <stdint.h>
#define RECEIPT ((volatile uint32_t *)0x2dfc0)
uint32_t boot_crc_hw(uint32_t crc,const void *data) {
    uint32_t feature;
    __asm__ volatile("mrc p15, 0, %0, c0, c2, 5":"=r"(feature));
    if (RECEIPT[0]!=0xa523cc01 || data==(void *)0x30000) {
        RECEIPT[0]=0xa523cc01;RECEIPT[3]=0;
    }
    RECEIPT[1]=feature;
    if (((feature>>16)&15)!=1 || ((uintptr_t)data&3)) {
        RECEIPT[2]=0;
        return ((uint32_t (*)(uint32_t,const void *))0x4cb00)(crc,data);
    }
    RECEIPT[2]=1;RECEIPT[3]++;
    const volatile uint32_t *p=data;
    for (unsigned i=0;i<128;i++) crc=__crc32w(crc,p[i]);
    return crc;
}
