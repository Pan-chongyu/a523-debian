/* SPDX-License-Identifier: MIT
 * Qualified CPU0-3 1416MHz/1150mV during exact-CID eMMC load and CRC.
 * SRAM code/data only. The original 480MHz/900mV state is restored before
 * TF-A/Linux and every normal failure return. DRAM and other PLLs untouched.
 */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define BIT(n) (1U<<(n))
#define TWI 0x07081400U
#define PLL 0x08817004U
#define MUX 0x08817060U
#define MAGIC 0xa523cf01U
extern void udelay(unsigned);
struct receipt {
    uint32_t magic,version,stage,active,initial_pll,initial_mux,initial_mv,sid;
    uint32_t peak_khz,peak_mv,final_pll,final_mux,final_mv,error,arm64_address,reserved;
    uint64_t boost_ticks,restore_ticks;
};
#define LOG ((volatile struct receipt *)0x2d500)
static uint64_t ticks(void) {uint64_t v;__asm__ volatile("mrrc p15,0,%Q0,%R0,c14":"=r"(v));return v;}
static int poll(unsigned address,unsigned mask,unsigned expected,unsigned tries)
{
    while(tries--) {if((REG(address)&mask)==expected)return 0;udelay(50);}
    return -1;
}
static int status(unsigned value)
{
    return poll(TWI+0xc,8,8,200) || REG(TWI+0x10)!=value;
}
static int start(unsigned value) {REG(TWI+0xc)=0x68;return status(value);}
static int send(unsigned value,unsigned expected) {REG(TWI+8)=value;REG(TWI+0xc)=0x48;return status(expected);}
static void stop(void) {REG(TWI+0xc)=0x58;poll(TWI+0xc,0x10,0,200);}
static int read_pmic(unsigned reg)
{
    int value=-1;
    if(start(8)||send(0x68,0x18)||send(reg,0x28)||start(0x10)||send(0x69,0x40))goto done;
    REG(TWI+0xc)=0x48;
    if(!status(0x58))value=REG(TWI+8)&255;
done:stop();return value;
}
static int set_voltage(unsigned target)
{
    int value=read_pmic(0x83);
    if(value<0 || (value&128)!=(LOG->initial_mv&128) || (value&127)<40 || (value&127)>65)return -1;
    if(target!=40 && target!=65)return -1;
    while((unsigned)(value&127)!=target) {
        unsigned next=value+((unsigned)(value&127)<target?1:-1);
        int fail=start(8)||send(0x68,0x18)||send(0x83,0x28)||send(next,0x28);
        stop();if(fail)return -1;
        udelay(350);
        value=read_pmic(0x83);if(value!=(int)next)return -1;
    }
    udelay(700);return 0;
}
static int commit(unsigned value)
{
    REG(PLL)=value|BIT(31)|BIT(30)|BIT(27)|BIT(29)|BIT(26);
    __asm__ volatile("dsb sy":::"memory");
    if(poll(PLL,BIT(26),0,200))return -1;
    REG(PLL)=REG(PLL)&~BIT(29);REG(PLL)=REG(PLL)|BIT(29);
    return poll(PLL,BIT(28),BIT(28),1400);
}
static int clock_to(unsigned n)
{
    REG(MUX)=(REG(MUX)&~(7U<<24))|(4U<<24);
    __asm__ volatile("dsb sy;isb":::"memory");udelay(1);
    if((REG(MUX)&(7U<<24))!=(4U<<24))return -1;
    if(commit((LOG->initial_pll&~(255U<<8))|(n<<8)))return -1;
    REG(MUX)=LOG->initial_mux;
    __asm__ volatile("dsb sy;isb":::"memory");udelay(1);
    return (REG(MUX)!=LOG->initial_mux || ((REG(PLL)>>8)&255)!=n)?-1:0;
}
__attribute__((noreturn)) static void fatal(void)
{
    LOG->error=0xcfdead;
    REG(0x07090110)=0xa523cfef;REG(0x07090118)=0xa52322ee;
    REG(0x0205000c)=0x14af;REG(0x02050010)=0x16aa0001;REG(0x02050014)=0x16aa0011;
    __asm__ volatile("dsb sy":::"memory");for(;;)__asm__ volatile("wfi");
}
void boot_cpu_restore(void)
{
    if(LOG->magic!=MAGIC || !LOG->active)return;
    if(clock_to(20))fatal();
    /* Keep initial lock-enable ownership and all nonfrequency mux bits. */
    REG(PLL)=(REG(PLL)&~BIT(29))|(LOG->initial_pll&BIT(29));
    if(set_voltage(40))fatal();
    LOG->final_pll=REG(PLL);LOG->final_mux=REG(MUX);LOG->final_mv=read_pmic(0x83);
    if(LOG->final_mux!=LOG->initial_mux || LOG->final_mv!=LOG->initial_mv)fatal();
    LOG->active=0;LOG->stage=4;LOG->restore_ticks=ticks();
}
int boot_cpu_performance_init(void)
{
    volatile uint32_t *words=(volatile uint32_t *)LOG;
    for(unsigned i=0;i<sizeof(*LOG)/4;i++)words[i]=0;
    LOG->magic=MAGIC;LOG->version=1;
    int result=((int(*)(void))0x4c700)();
    if(result) {LOG->stage=10;return result;}
    LOG->stage=1;LOG->initial_pll=REG(PLL);LOG->initial_mux=REG(MUX);LOG->sid=REG(0x03006248);
    if(LOG->sid!=0x48 || ((LOG->initial_pll>>8)&255)!=20 ||
       (LOG->initial_pll&0xc8000000U)!=0xc8000000U ||
       (LOG->initial_pll&0x003f0007U) || (LOG->initial_mux&(0x07000000U|0x00030000U))!=0x03000000U) {
        LOG->stage=11;return 0;
    }
    int id=read_pmic(3),mv=read_pmic(0x83);LOG->initial_mv=mv;
    if(id!=0xff || mv<0 || (mv&127)!=40) {LOG->stage=12;return 0;}
    LOG->active=1;
    if(set_voltage(65)) {LOG->error=1;boot_cpu_restore();return 0;}
    LOG->peak_mv=1150;
    if(clock_to(59)) {LOG->error=2;boot_cpu_restore();return 0;}
    LOG->peak_khz=1416000;LOG->stage=2;LOG->boost_ticks=ticks();
    return 0;
}
__attribute__((noreturn)) void boot_cpu_performance_handoff(unsigned address)
{
    boot_cpu_restore();LOG->arm64_address=address;
    __asm__ volatile("dsb sy;isb":::"memory");
    ((void(*)(unsigned))0x4403c)(address);for(;;)__asm__ volatile("wfi");
}
/* Patched at the common pop, after the original stack-local adjustment. */
__attribute__((naked)) void boot_cpu_performance_failure(void)
{
    __asm__ volatile("push {r0-r3,r12,lr}\nsub sp,sp,#4\nbl boot_cpu_restore\n"
        "add sp,sp,#4\npop {r0-r3,r12,lr}\npop {r4-r11,pc}");
}
