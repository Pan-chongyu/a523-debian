/* SPDX-License-Identifier: GPL-2.0-or-later
 * SRAM-only early panel feedback for the exact TZX P30 A523 board.
 * DSI/PHY/TCON sequences are adapted from the already hardware-qualified
 * screen-poweron source, derived from Allwinner's GPL display drivers.
 * No framebuffer, DRAM, eMMC, CPU/DDR PLL or new PMIC voltage programming.
 */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define BIT(n) (1U << (n))
#define CCU 0x02001000U
#define PIO 0x02000000U
#define HOST 0x05508000U
#define PHY 0x05509000U
#define TCON 0x05502000U
#define TOP 0x05500000U
#define PWM 0x02000c00U
#define TWI 0x07081400U
#define MAGIC 0xa523ed01U
extern void udelay(unsigned);

struct saved_reg { uint32_t address, mask, original; };
struct panel_receipt {
    uint32_t magic, version, stage, active, pmic_original, count;
    uint64_t entered_ticks, lit_ticks;
    uint32_t panel_id, panel_status, phy_debug, line_before, line_after;
    struct saved_reg regs[24];
    uint32_t diagnostics[17];
};
#define LOG ((volatile struct panel_receipt *)0x2d200)
static const struct saved_reg specs[] = {
    {CCU+0xb28, 0x8700001f, 0}, {CCU+0xb4c, 0x00020002, 0},
    {CCU+0xb64, BIT(31), 0}, {CCU+0xb70, BIT(31), 0},
    {CCU+0xb7c, 0x00020002, 0}, {CCU+0xabc, 0x00010001, 0},
    {CCU+0x7ac, 0x00010001, 0},
    {PIO+0x94, 0xffffff00, 0}, {PIO+0x98, 0xff00ffff, 0},
    {PIO+0xa0, 0x00c00000, 0}, {PIO+0x158, 0x0000ff00, 0},
    {PIO+0x160, 0x000c0000, 0},
    {PWM+0x20, 0xffffffff, 0}, {PWM+0x40, 0x00010001, 0},
    {PWM+0x80, BIT(0), 0}, {PWM+0x100, 0xffffffff, 0},
    {PWM+0x104, 0xffffffff, 0},
    {TOP+0x04, BIT(4), 0}, {TOP+0x0c, BIT(1)|BIT(5), 0},
    {TOP+0x20, BIT(17), 0}
};
#define COUNT (sizeof(specs)/sizeof(specs[0]))

uint64_t __attribute__((noinline)) panel_ticks(void)
{
    uint64_t value;
    __asm__ volatile("mrrc p15, 0, %Q0, %R0, c14" : "=r"(value));
    return value;
}
static void change(unsigned address, unsigned mask, unsigned value)
{
    REG(address)=(REG(address)&~mask)|(value&mask);
}
static void delay(unsigned us)
{
    REG(0x0205000c)=0x14af;
    udelay(us);
}
static int poll(unsigned address, unsigned mask, unsigned expected, unsigned count)
{
    while (count--) {
        if ((REG(address)&mask)==expected) return 0;
        delay(50);
    }
    return -1;
}
static int twi_status(unsigned value)
{
    if (poll(TWI+0x0c,8,8,200)) return -1;
    return REG(TWI+0x10)==value ? 0 : -1;
}
static int twi_start(unsigned status)
{
    REG(TWI+0x0c)=0x68;
    return twi_status(status);
}
static int twi_send(unsigned value,unsigned status)
{
    REG(TWI+8)=value;
    REG(TWI+0x0c)=0x48;
    return twi_status(status);
}
static void twi_stop(void)
{
    REG(TWI+0x0c)=0x58;
    poll(TWI+0x0c,0x10,0,200);
}
static int pmic_read(unsigned reg)
{
    int value=-1;
    if (twi_start(8)||twi_send(0x68,0x18)||twi_send(reg,0x28)||
        twi_start(0x10)||twi_send(0x69,0x40)) goto done;
    REG(TWI+0x0c)=0x48;
    if (!twi_status(0x58)) value=REG(TWI+8)&255;
done:
    twi_stop();
    return value;
}
static int pmic_rail(unsigned value)
{
    /* The original voltage hook has already set up and checked R_TWI0.
     * Only the known CLDO enable register can be written here. */
    if (value!=0xd5 && value!=0xd7 && value!=0xdd && value!=0xdf) return -1;
    int failed=twi_start(8)||twi_send(0x68,0x18)||twi_send(0x91,0x28)||twi_send(value,0x28);
    twi_stop();
    return failed ? -1 : 0;
}
static uint32_t header(unsigned type,unsigned data)
{
    static const unsigned masks[]={0xf12cb7,0xf2555b,0x749a6d,0xb8e38e,0xdf03f0,0xeffc00};
    unsigned value=type|(data<<8),ecc=0;
    for (unsigned i=0;i<6;i++) {
        unsigned x=value&masks[i];
        x^=x>>16;x^=x>>8;x^=x>>4;x^=x>>2;x^=x>>1;
        ecc|=(x&1)<<i;
    }
    return value|(ecc<<24);
}
static int packet(unsigned type,unsigned data,int receive)
{
    LOG->diagnostics[4]=type;LOG->diagnostics[5]=data;
    REG(HOST+0x200)=BIT(26)|BIT(25)|BIT(9);
    REG(HOST+0x300)=header(type,data);
    REG(HOST+0x200)=3;
    REG(HOST+0x48)=receive ? (4|(7U<<16)|(1U<<28)|(15U<<4)) : (4|(15U<<16));
    REG(HOST+0x10)=3<<16;
    REG(HOST+0x10)=(3<<16)|1;
    int result=poll(HOST+0x10,1,0,400);
    LOG->diagnostics[6]=result;LOG->diagnostics[7]=REG(HOST+0x200);
    LOG->diagnostics[8]=REG(HOST+0x240);LOG->diagnostics[9]=REG(HOST+0x2f0);
    if (!result) return 0;
    REG(HOST+0x10)=3<<16;
    return -1;
}
static int read_dcs(unsigned command)
{
    if (packet(0x37,8,0)||packet(0x06,command,1)) return -1;
    unsigned ctl=REG(HOST+0x200),h=REG(HOST+0x240);
    if (ctl&BIT(26)) return -1;
    switch (h&0x3f) {
    case 0x21: case 0x22: return (h>>8)&255;
    case 0x1c:
        if (((h>>8)&65535)<1 || ((h>>8)&65535)>8) return -1;
        return REG(HOST+0x244)&255;
    }
    return -1;
}
static unsigned zero_crc(unsigned bytes)
{
    unsigned crc=65535;
    while (bytes--) for (unsigned bit=0;bit<8;bit++)
        crc=(crc>>1)^((crc&1)?0x8408:0);
    return crc;
}
static void cleanup(void)
{
    /* No Linux owner exists here. End the pattern before restoring rails. */
    if (LOG->count==COUNT) {
        REG(PWM+0x80)=0;
        REG(HOST+0x10)=3<<16;
        REG(TCON)=0;
        REG(TCON+0x40)=0;
        change(PHY+0x108,BIT(22)|BIT(21),0);
        change(PHY+0x104,BIT(20)|BIT(21)|BIT(22),0);
    }
    for (unsigned i=LOG->count;i;i--) {
        volatile const struct saved_reg *s=&LOG->regs[i-1];
        change(s->address,s->mask,s->original);
    }
    if (LOG->pmic_original==0xd5 || LOG->pmic_original==0xd7)
        pmic_rail(LOG->pmic_original);
    /* No later boot code has run yet, so these exact pre-hook values still
     * own their PLLs. Successful handoff leaves PLLs to Linux CCF instead. */
    if (LOG->diagnostics[16]&2) REG(CCU+0x40)=LOG->diagnostics[1];
    if (LOG->diagnostics[16]&1) REG(CCU+0x20)=LOG->diagnostics[0];
    LOG->active=0;
    __asm__ volatile("dsb sy" ::: "memory");
}
static int display_parents(void)
{
    /* Exact PERIPH0 factors from sun55iw3 SyterKit; VIDEO0 factors match
     * the qualified native clock tree. Do not reprogram a live parent. */
    const unsigned offsets[]={0x20,0x40};
    const unsigned factors[]={0x00216310,0x00006201};
    for (unsigned i=0;i<2;i++) {
        unsigned original=LOG->diagnostics[i],address=CCU+offsets[i];
        if ((original&BIT(31)) && (original&0xffffff)!=factors[i]) return -1;
        LOG->diagnostics[16]|=BIT(i);
        if (!(original&BIT(31))) REG(address)=0x48000000|factors[i];
        change(address,BIT(29)|BIT(30)|BIT(31)|BIT(27),
            BIT(29)|BIT(30)|BIT(31)|BIT(27));
        if (poll(address,BIT(28),BIT(28),4000)) return -1;
        LOG->diagnostics[2+i]=REG(address);
    }
    return 0;
}
static int panel_start(void)
{
#ifdef TZX_PANEL_OVERLAP
    if (LOG->stage!=2 || (LOG->pmic_original!=0xd5 && LOG->pmic_original!=0xd7) ||
        pmic_read(0x91)!=(int)(LOG->pmic_original|8)) return -1;
    uint64_t elapsed=panel_ticks()-*(volatile uint64_t *)0x2d740U;
    if (elapsed<24000000U) delay(1000001U-(unsigned)elapsed/24);
#else
    LOG->stage=2;
    if (pmic_read(0x9b)!=0x0d || pmic_read(0x9e)!=0x1c) return -1;
    int original=pmic_read(0x91);
    if (original!=0xd5 && original!=0xd7) return -1;
    LOG->pmic_original=original;
    if (pmic_rail(original|8)||pmic_read(0x91)!=(original|8)) return -1;
    delay(1000000); /* Preserve the qualified panel rail settling interval. */
#endif
    LOG->stage=3;
    /* Display blocks must be reset and unused, as in the qualified driver. */
    if ((REG(CCU+0xb4c)&0x20002)||(REG(CCU+0xb7c)&0x20002)||
        (REG(CCU+0xabc)&0x10001)||(REG(CCU+0x7ac)&0x10001)) return -1;
    /* Snapshot gated registers only after enabling their bus clocks. */
    for (unsigned i=0;i<12;i++) {
        LOG->regs[i]=specs[i];LOG->regs[i].original=REG(specs[i].address);
    }
    LOG->count=12;
    if (display_parents()) return -1;
    change(CCU+0xb28,0x8700001f,0x82000000); /* Qualified 150 MHz DSI parent. */
    change(CCU+0xb4c,0x20002,0x20002);
    change(CCU+0xb64,BIT(31),BIT(31));change(CCU+0xb70,BIT(31),BIT(31));
    change(CCU+0xb7c,0x20002,0x20002);change(CCU+0xabc,0x10001,0x10001);
    change(CCU+0x7ac,0x10001,0x10001);
    delay(100);
    for (unsigned i=12;i<COUNT;i++) {
        LOG->regs[i]=specs[i];LOG->regs[i].original=REG(specs[i].address);
    }
    LOG->count=COUNT;
    change(PIO+0xa0,BIT(22)|BIT(23),0);
    change(PIO+0x98,0xff000000,0x11000000); /* reset and backlight low */
    change(PIO+0x160,BIT(18)|BIT(19),0);
    change(PIO+0x158,0xff00,0x1100);
    /* Verified four-lane 432MHz PHY, with 72MHz LS pixel clock. */
    REG(PHY+0x10)=0x0406000e;REG(PHY+0x14)=0x0a033207;
    REG(PHY+0x18)=30;REG(PHY+0x1c)=0;REG(PHY+0x20)=0x303;
    change(PHY+0x58,0xf0000000,0xf0000000);
    change(PHY+0x54,0x0f000000,0x0f000000);
    change(PHY,0x30,0x30);
    REG(PHY+0x5c)=0x844635ee;
    change(PHY+0x54,BIT(4)|BIT(1),BIT(4)|BIT(1));
    change(PHY+0x58,BIT(18)|BIT(24)|BIT(25),BIT(18)|BIT(24)|BIT(25));
    REG(PHY+0x4c)=0x44;REG(PHY+0x110)=0x0b;REG(PHY+0x118)=20;
    delay(1);
    change(PHY+0x58,BIT(27)|BIT(26),BIT(27)|BIT(26));
    change(PHY+0x50,BIT(31),BIT(31));change(PHY,1,1);
    REG(PHY+0x4c)=0x77;REG(PHY+0x5c)=0x84363538;
    REG(PHY+0x104)=BIT(31)|BIT(22)|BIT(20)|(3U<<28)|(5U<<24)|(72U<<8)|3;
    REG(PHY+0x10c)=0;
    change(PHY+4,BIT(26)|BIT(28),BIT(28));
    change(PHY+0x104,BIT(20)|BIT(21)|BIT(22)|BIT(31),BIT(20)|BIT(21)|BIT(22)|BIT(31));
    change(PHY+0x108,BIT(22)|BIT(21)|BIT(12),BIT(22)|BIT(21)|BIT(12));
    LOG->stage=4;
    if (poll(PHY+0xe0,BIT(26),BIT(26),4000)) return -1;
    LOG->phy_debug=REG(PHY+0xe0);
    change(PIO+0x160,BIT(18),BIT(18));delay(5000);
    change(PIO+0x160,BIT(19),BIT(19));delay(40000);
    delay(20000);change(PIO+0xa0,BIT(22),BIT(22));delay(120000);
    change(PIO+0x94,0xffffff00,0x44444400);
    change(PIO+0x98,0x0000ffff,0x4444);
    LOG->diagnostics[11]=REG(PIO+0x380);LOG->diagnostics[12]=REG(PIO+0x384);
    LOG->diagnostics[13]=REG(PIO+0x388);LOG->diagnostics[14]=REG(PIO+0xa0);
    LOG->diagnostics[15]=REG(PIO+0x160);
    REG(HOST+4)=0;REG(HOST+0x0c)=0;REG(HOST+0x10)=3<<16;REG(HOST+0x14)=0;
    REG(HOST+0x20)=0x1f;REG(HOST+0x24)=0x10000001;REG(HOST+0x30)=0x30100001;
    REG(HOST+0x3c)=0x5000001f;REG(HOST+0x40)=0x30000002;
    REG(HOST+0x44)=49;REG(HOST+0x54)=49;REG(HOST+0x4c)=0;REG(HOST+0x50)=0;
    REG(HOST+0x60)=10;REG(HOST+0x78)=0;REG(HOST)=1;delay(20000);
    LOG->stage=5;
    int a=read_dcs(0xda),b=read_dcs(0xdb),c=read_dcs(0xdc);
    LOG->diagnostics[10]=REG(PHY+0xe0);
    LOG->panel_id=((unsigned)a<<16)|((unsigned)b<<8)|(unsigned)c;
    if (a!=0x93||b!=0x65||c!=4) return -1;
    const unsigned unlock[]={0x00e0,0x93e1,0x65e2,0xf8e3,0x773a};
    for (unsigned i=0;i<5;i++) if (packet(0x15,unlock[i],0)) return -1;
    if (packet(0x05,0x11,0)) return -1;
    delay(150000);
    if (packet(0x05,0x29,0)) return -1;
    delay(150000);
    LOG->panel_status=read_dcs(0x0a);
    if (LOG->panel_status==0xffffffff || !(LOG->panel_status&16)) return -1;
    LOG->stage=6;
    change(TOP+0x0c,BIT(1)|BIT(5),BIT(1)|BIT(5));
    change(TOP+4,BIT(4),0);change(TOP+0x20,BIT(17),BIT(17));
    REG(TCON)=0;REG(TCON+4)=0;REG(TCON+0x10)=0;REG(TCON+0x3c)=0;
    REG(TCON+0x40)=1|(2U<<4)|BIT(24);REG(TCON+0x44)=1;
    REG(TCON+0x48)=(799U<<16)|1279;
    REG(TCON+0x4c)=(879U<<16)|39;REG(TCON+0x50)=(2606U<<16)|10;
    REG(TCON+0x54)=(19U<<16)|3;REG(TCON+0x58)=0;
    REG(TCON+0x88)=0;REG(TCON+0x8c)=0xe0000000;REG(TCON+0xf8)=8;
    REG(TCON+0x160)=(40U<<16)|799;REG(TCON+0x164)=1279;
    REG(TCON+0x168)=(329U<<16)|10;REG(TCON+0x16c)=0;
    REG(TCON+0x230)=0;REG(TCON+0x234)=0;REG(TCON+0x1f0)=(1080U<<16)|3;
    REG(TCON+0x60)=BIT(28)|BIT(16)|BIT(2)|1;
    if (packet(0x05,0x13,0)) return -1;
    REG(HOST+0x20)=0x1f;REG(HOST+0x28)=0x20000010;REG(HOST+0x48)=0xf02;
    REG(HOST+0x10)=3<<16;REG(HOST+0x10)=(3<<16)|1;
    if (poll(HOST+0x10,1,0,400)) return -1;
    REG(HOST+0x20)=0x0f;delay(1000);
    REG(HOST+0x10)=3<<16;REG(HOST+0x0c)=0;REG(HOST+0x14)=0x17;
    REG(HOST+0x18)=(7U<<16)|4;REG(HOST+0x1c)=(1303U<<16)|1280;
    REG(HOST+0x20)=0x0f;REG(HOST+0x28)=0x20000010;REG(HOST+0x2c)=0x2000000f;
    REG(HOST+0x34)=0x40000010;REG(HOST+0x38)=0x0f;REG(HOST+0x3c)=0x5000001f;
    REG(HOST+0x44)=(49U<<16)|49;REG(HOST+0x54)=(49U<<16)|49;
    REG(HOST+0x4c)=(5U<<20)|(6U<<16)|1;REG(HOST+0x7c)=BIT(28)|15;
    REG(HOST+0x80)=BIT(16)|8;REG(HOST+0x90)=header(0x3e,2400);
    REG(HOST+0x98)=65535;REG(HOST+0x9c)=0xffffffff;
    const unsigned kinds[]={0x21,0x31,1,0x11};
    for (unsigned i=0;i<4;i++) REG(HOST+0xb0+4*i)=header(kinds[i],0);
    const unsigned offsets[]={0xc0,0xc8,0xd0,0xe0,0xe8};
    const unsigned sizes[]={50,54,104,2570,4};
    for (unsigned i=0;i<5;i++) {
        REG(HOST+offsets[i])=header(0x19,sizes[i]);
        REG(HOST+offsets[i]+4)=zero_crc(sizes[i])<<16;
    }
#ifdef TZX_PANEL_OVERLAP
    REG(HOST+0x2f8)=BIT(28); /* Fixed black until the exact image commits. */
#else
    REG(HOST+0x2f8)=0xff;
#endif
    REG(TCON+0x40)|=BIT(31);REG(TCON)=BIT(31);
    REG(TCON+0x44)=0xf0000001;
    REG(HOST+0x48)=6|(3U<<24)|(7U<<12)|(6U<<28)|(15U<<20);
    REG(HOST+0x10)=(3<<16)|1;
    LOG->line_before=REG(HOST+0x2e0);delay(100000);
    LOG->line_after=REG(HOST+0x2e0);
    if (!(REG(HOST+0x10)&1) || LOG->line_before==LOG->line_after) return -1;
    LOG->stage=7;
    REG(PWM+0x20)=0;REG(PWM+0x104)=(479U<<16)|96;
    REG(PWM+0x100)=BIT(8);change(PWM+0x40,BIT(16)|1,1);REG(PWM+0x80)=0;
    change(PIO+0x98,0xf0000000,0x20000000);
    __asm__ volatile("dsb sy" ::: "memory");
    REG(PWM+0x80)=1;
    LOG->lit_ticks=panel_ticks();LOG->active=1;
    return 0;
}

int boot_panel_voltage_entry(unsigned millivolts)
{
    /* Preserve the exact trained-voltage entry and its return convention. */
    int result=((int (*)(unsigned))0x4ba44)(millivolts);
    if (result) return result;
    LOG->magic=MAGIC;LOG->version=2;LOG->stage=1;LOG->active=0;
    LOG->pmic_original=0xffffffff;LOG->count=0;
    LOG->entered_ticks=panel_ticks();LOG->lit_ticks=0;
    LOG->panel_id=0;LOG->panel_status=0;LOG->phy_debug=0;
    LOG->line_before=0;LOG->line_after=0;
    for (unsigned i=0;i<17;i++) LOG->diagnostics[i]=0;
    LOG->diagnostics[0]=REG(CCU+0x20);LOG->diagnostics[1]=REG(CCU+0x40);
#ifdef TZX_PANEL_OVERLAP
    LOG->stage=2;
    if (pmic_read(0x9b)!=0x0d || pmic_read(0x9e)!=0x1c) goto failed;
    int original=pmic_read(0x91);
    if (original!=0xd5 && original!=0xd7) goto failed;
    LOG->pmic_original=original;
    if (pmic_rail(original|8)||pmic_read(0x91)!=(original|8)) goto failed;
    *(volatile uint64_t *)0x2d740U=panel_ticks();
    return result;
failed:
    LOG->stage|=0xe0000000;
    cleanup();
#else
    if (panel_start()) {
        LOG->stage|=0xe0000000;
        cleanup();
    } else LOG->stage=0x100;
#endif
    __asm__ volatile("dsb sy" ::: "memory");
    return result; /* Display failure must not stop the known DRAM boot. */
}

#ifdef TZX_PANEL_OVERLAP
void boot_panel_finish(void)
{
    if (LOG->magic!=MAGIC || LOG->version!=2 || LOG->stage!=2) return;
    if (panel_start()) {
        LOG->stage|=0xe0000000;
        cleanup();
    } else LOG->stage=0x100;
    __asm__ volatile("dsb sy" ::: "memory");
}
void boot_panel_cancel(void)
{
    if (LOG->magic==MAGIC && LOG->version==2 && LOG->stage==2) cleanup();
}
#endif
