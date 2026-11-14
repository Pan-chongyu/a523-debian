/* SPDX-License-Identifier: GPL-2.0-or-later
 * Post-training DE350 boot splash. Display programming is derived from the
 * qualified tzx_de_scanout.c. No PMIC, DDR or CPU frequency writes here.
 * The complete executable and RLE asset are CRC-bound by the signed SRAM hook.
 */
#include <stdint.h>
#include "logo_config.h"
#define REG(a) (*(volatile uint32_t *)(a))
#define BIT(n) (1U<<(n))
#define DE 0x05000000U
#define CCU 0x02001000U
#define HOST 0x05508000U
#define TCON 0x05502000U
#define TOP 0x05500000U
#define SIZE ((1279U<<16)|799)
#define FB ((volatile uint32_t *)0x42400000U)
#define RCQ ((volatile uint32_t *)0x42800000U)
struct receipt {
    uint32_t magic,version,stage,active,error,sectors,crc,bytes;
    uint64_t entered,loaded,lit;
    uint32_t de_clock,de_bgr,top_route,tcon_source,dsi_jump,de_version;
    uint32_t rcq_status,ovl_address,line_before,line_after,pixel_count,reserved;
};
#define LOG ((volatile struct receipt *)0x2d600U)
extern void udelay(unsigned);
static uint64_t ticks(void) {uint64_t v;__asm__ volatile("mrrc p15,0,%Q0,%R0,c14":"=r"(v));return v;}
static void change(unsigned a,unsigned m,unsigned v) {REG(a)=(REG(a)&~m)|(v&m);}
static int poll(unsigned a,unsigned mask,unsigned expected,unsigned tries)
{
    while(tries--) {if((REG(a)&mask)==expected)return 0;udelay(50);}
    return -1;
}
struct block {uint32_t offset,size,shadow;};
static const struct block blocks[]={
    {0x1c1000,0x80,0x200},{0x1c1080,0xc,0x280},{0x1c10e0,0x1c,0x2a0},
    {0x281000,0x60,0x300},{0x281080,0x24,0x380},{0x2810a0,0x60,0x3c0},
    {0x285000,0x2c,0x440},{0x1c4000,0x88,0x480},{0x1c5000,0x58,0x520},
    {0x1c5400,0x34,0x580},{0x1c0800,4,0x5c0},{0x1c8000,4,0x5e0},
    {0x28b000,4,0x600},{0x28b100,4,0x620}
};
static void sw(unsigned b,unsigned off,unsigned value) {RCQ[(blocks[b].shadow+off)/4]=value;}
static int decode(void)
{
    const uint32_t *p=(const uint32_t *)(0x42000000U+LOGO_CODE_SPACE);
    const uint32_t *end=p+LOGO_RLE_BYTES/4;
    unsigned pixels=0;
    while(p<end) {
        unsigned token=*p++,n=token&0x7fffffffU;
        if(!n || n>1024000-pixels)return -1;
        if(token&BIT(31)) {
            if(p==end)return -1;
            unsigned value=*p++;
            while(n--)FB[pixels++]=value;
        } else {
            if((unsigned)(end-p)<n)return -1;
            while(n--)FB[pixels++]=*p++;
        }
    }
    LOG->pixel_count=pixels;
    __asm__ volatile("dsb sy":::"memory");
    return pixels==1024000?0:-1;
}
static int pause(void)
{
    REG(HOST+0x4c)|=BIT(28);
    return poll(HOST+0x10,1,0,1200);
}
static int resume(void)
{
    unsigned jump=REG(HOST+0x48);
    REG(HOST+0x20)=0x1f;REG(HOST+0x48)=0xf02;
    REG(HOST+0x10)=3<<16;REG(HOST+0x10)=(3<<16)|1;
    if(poll(HOST+0x10,1,0,800))return -1;
    REG(HOST+0x20)=0xf;REG(HOST+0x48)=jump;REG(HOST+0x4c)=LOG->dsi_jump;
    REG(HOST+0x10)=3<<16;REG(HOST+0x10)=(3<<16)|1;
    return 0;
}
static void stop_de(void)
{
    REG(DE+0x8110)=0;REG(DE+0x8100)=0;REG(DE+0x8008)=0;REG(DE+0x8000)=0;
    change(TOP+0x1c,255,LOG->top_route);
    change(CCU+0x60c,BIT(16),0);udelay(10);
    change(CCU+0x60c,0x10001,LOG->de_bgr);
    change(CCU+0x600,0x8700001f,LOG->de_clock);
}
int boot_logo_show(void)
{
    LOG->stage=3;
    if(decode()) {LOG->error=3;return -1;}
    /* Exact qualified board defaults. Unknown owners are left untouched. */
    if((REG(0x07065008)&15)!=8 || (REG(CCU+0x60c)&0x10001) ||
       !(REG(TCON+0x40)&BIT(31)) || !(REG(HOST+0x10)&1)) {LOG->error=4;return -1;}
    LOG->de_clock=REG(CCU+0x600);LOG->de_bgr=REG(CCU+0x60c);
    LOG->top_route=REG(TOP+0x1c);LOG->tcon_source=REG(TCON+0x40);LOG->dsi_jump=REG(HOST+0x4c);
    change(CCU+0x600,0x8700001f,0x80000000);change(CCU+0x60c,0x10001,0x10001);udelay(100);
    LOG->de_version=REG(DE+0x8014);
    if(LOG->de_version!=0x03500200) {LOG->error=5;stop_de();return -1;}
    for(unsigned i=0;i<1024;i++)RCQ[i]=0;
    for(unsigned i=0;i<sizeof(blocks)/sizeof(blocks[0]);i++) {
        RCQ[i*4]=0x42800000+blocks[i].shadow;RCQ[i*4+1]=blocks[i].size;
        RCQ[i*4+2]=1;RCQ[i*4+3]=blocks[i].offset;
    }
    sw(0,0,0xff000403);sw(0,4,SIZE);sw(0,0xc,3200);sw(0,0x10,0x42400000);
    sw(1,8,SIZE);sw(3,0,BIT(8));sw(3,4,0xff000000);sw(3,8,SIZE);
    sw(4,8,0xff000000);sw(4,0xc,SIZE);sw(4,0x10,0x03010301);sw(7,0x44,255);
    __asm__ volatile("dsb sy":::"memory");
    change(TOP+0x1c,255,0xf1);REG(DE+0x8004)=0x10001;REG(DE+0x8000)=0x10001;REG(DE+0x8008)=1;
    change(DE+0x8024,3U<<16,0);change(DE+0x8028,15,8);change(DE+0x8010,255,0xf1);
    REG(DE+0x804c)=0;REG(DE+0x8050)=0x6000;REG(DE+0x8108)=SIZE;REG(DE+0x810c)=1;
    REG(DE+0x8114)=0x42800000;REG(DE+0x8118)=0;REG(DE+0x811c)=sizeof(blocks)/sizeof(blocks[0])*16;
    REG(DE+0x8100)=BIT(0)|BIT(6)|BIT(7);
    unsigned n;
    for(n=0;n<2500;n++) {if(((REG(TCON+0xfc)>>16)&0x1fff)>100)break;udelay(20);}
    if(n==2500) {LOG->error=6;stop_de();return -1;}
    REG(DE+0x8104)=BIT(0)|BIT(2)|BIT(3);REG(DE+0x8110)=1;
    if(poll(DE+0x8104,BIT(2),BIT(2),2000)) {LOG->error=7;stop_de();return -1;}
    LOG->rcq_status=REG(DE+0x8104);LOG->ovl_address=REG(DE+0x1c1010);
    if(LOG->ovl_address!=0x42400000 || pause()) {LOG->error=8;resume();stop_de();return -1;}
    REG(TCON+0x40)=LOG->tcon_source&~7U;
    if(resume()) {LOG->error=9;REG(TCON+0x40)=LOG->tcon_source;resume();stop_de();return -1;}
    REG(HOST+0x2f8)=0xff; /* Drop fixed black only after an RCQ-complete image. */
    REG(0x02000c80)=1;
    LOG->line_before=REG(HOST+0x2e0);udelay(35000);LOG->line_after=REG(HOST+0x2e0);
    LOG->active=1;LOG->stage=0x100;LOG->lit=ticks();
    __asm__ volatile("dsb sy":::"memory");
    return 0;
}
