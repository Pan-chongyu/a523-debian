/* SPDX-License-Identifier: MIT */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define HEADER ((uint32_t *)0x30000)
extern int cold_emmc_init(void);
extern int cold_emmc_read(unsigned,void *);
extern int cold_emmc_slower(void);
extern void enter_arm64(unsigned);

static uint32_t crc32_update(uint32_t crc,const void *data,unsigned bytes) {
    const unsigned char *p=data;
    while(bytes--) {
        crc^=*p++;
        for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320&-(crc&1));
    }
    return crc;
}
static void error(unsigned stage,unsigned detail) {
    REG(0x07090110)=stage;REG(0x07090114)=detail;
    __asm__ volatile("dsb sy":::"memory");
}
void chain_load(void) {
    REG(0x07090110)=0xa5234701;
    if(cold_emmc_init()){error(0xa52347e0,0);return;}
    if(cold_emmc_read(4096,HEADER)){error(0xa52347e1,4096);return;}
    if(HEADER[0]!=0x33323541||HEADER[1]!=0x31444e42||HEADER[2]!=1||HEADER[3]!=5){
        error(0xa52347e2,HEADER[0]);return;
    }
    uint32_t expected=HEADER[4];HEADER[4]=0;
    if(~crc32_update(~0U,HEADER,512)!=expected){error(0xa52347e3,expected);return;}
    const unsigned targets[]={0x48080000,0x47000000,0x60000000,0x4a000000,0x54000};
    const unsigned maximum[]={0x1f80000,0x100000,0x1000000,0x100000,0xc000};
    for(unsigned i=0;i<5;i++) {
        const uint32_t *item=HEADER+8+i*6;
        unsigned lba=item[0],bytes=item[1],address=item[2],crc=item[3];
        unsigned rounded=(bytes+511)&~511U;
        if(address!=targets[i]||!bytes||bytes>maximum[i]||rounded>maximum[i]||
           lba<4097||lba>=131072||rounded/512>131072-lba){error(0xa52347e4,i);return;}
        unsigned valid=0;
        for(unsigned attempt=0;attempt<2&&!valid;attempt++) {
            REG(0x07090110)=0xa5234710+i;
            uint32_t actual=~0U;
            for(unsigned offset=0;offset<rounded;offset+=512) {
                if(cold_emmc_read(lba+offset/512,(void *)(address+offset))){
                    error(0xa52347f0+i,lba+offset/512);return;
                }
                actual=crc32_update(actual,(void *)(address+offset),512);
                REG(0x0205000c)=0x14af;
            }
            valid=(~actual==crc);
            if(!valid) {
                REG(0x07090108)=actual;REG(0x0709010c)=crc;
                if(cold_emmc_slower()){error(0xa52347e5,i);return;}
            }
        }
        if(!valid){error(0xa52347c0+i,lba);return;}
    }
    REG(0x0200190c)|=(1U<<16)|1;
    REG(0x02000034)=(REG(0x02000034)&~0xff0U)|0x220;
    REG(0x07090110)=0xa5234704;
    REG(0x0205000c)=0x14af;
    __asm__ volatile("dsb sy; isb":::"memory");
    enter_arm64(0x54000);
}
