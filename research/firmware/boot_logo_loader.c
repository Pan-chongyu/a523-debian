/* SPDX-License-Identifier: MIT
 * Bounded optional splash load after the original exact-CID/CPU wrapper.
 * An absent/corrupt image never prevents the existing Debian boot.
 */
#include <stdint.h>
#include "logo_config.h"
#define REG(a) (*(volatile uint32_t *)(a))
struct receipt {
    uint32_t magic,version,stage,active,error,sectors,crc,bytes;
    uint64_t entered,loaded,lit;
    uint32_t rest[12];
};
#define LOG ((volatile struct receipt *)0x2d600U)
static uint64_t ticks(void) {uint64_t v;__asm__ volatile("mrrc p15,0,%Q0,%R0,c14":"=r"(v));return v;}
int boot_logo_init(void)
{
    int result=((int(*)(void))0x4e6a4)();
    volatile uint32_t *p=(volatile uint32_t *)LOG;
    for(unsigned i=0;i<sizeof(*LOG)/4;i++)p[i]=0;
    LOG->magic=0xa523b001;LOG->version=1;LOG->entered=ticks();
    if(result) {LOG->error=10;return result;}
    unsigned control;
    __asm__ volatile("mrc p15,0,%0,c1,c0,0":"=r"(control));
    if((control&5) || REG(0x2d200)!=0xa523ed01 || REG(0x2d20c)!=1) {LOG->error=11;return 0;}
    LOG->stage=1;LOG->bytes=LOGO_PAYLOAD_BYTES;
    unsigned crc=0xffffffff;
    for(unsigned sector=0;sector<LOGO_PAYLOAD_BYTES/512;sector++) {
        uint32_t *staging=(uint32_t *)0x30200;
        if(((int(*)(unsigned,void *))0x44bac)(LOGO_LBA+sector,staging)) {LOG->error=1;return 0;}
        volatile uint32_t *out=(volatile uint32_t *)(0x42000000+sector*512);
        for(unsigned i=0;i<128;i++)out[i]=staging[i];
        __asm__ volatile("dsb sy":::"memory");
        for(unsigned i=0;i<128;i++)if(out[i]!=staging[i]) {LOG->error=12;return 0;}
        crc=((unsigned(*)(unsigned,const void *))0x4ce00)(crc,staging);
        LOG->sectors=sector+1;
    }
    LOG->crc=~crc;LOG->loaded=ticks();
    if(LOG->crc!=LOGO_PAYLOAD_CRC) {LOG->error=2;return 0;}
    unsigned zero=0;
    __asm__ volatile("dsb sy\nmcr p15,0,%0,c7,c5,0\nmcr p15,0,%0,c7,c5,6\ndsb sy\nisb"::"r"(zero):"memory");
    LOG->stage=2;
    ((int(*)(void))LOGO_ENTRY)();
    return 0;
}
