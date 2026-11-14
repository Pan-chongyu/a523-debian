/* SPDX-License-Identifier: MIT
 * Apply the already qualified CPUA boost before DRAM software training.
 * Original CPU guard, voltage ramp, PLL update and restore routines are reused.
 * DRAM parameters, geometry scanning, PHY training and delay callbacks stay intact.
 */
#include <stdint.h>

struct speed_receipt {
    uint32_t magic, version, voltage_result, boost_attempted;
    uint64_t entered_ticks, boosted_ticks, trained_ticks, returned_ticks;
};
#define LOG ((volatile struct speed_receipt *)0x2d700U)
extern int original_panel_voltage(unsigned millivolts);
extern int original_cpu_boost(void);
extern int original_card_init(void);
extern void original_cpu_restore(void);
#ifdef TZX_PANEL_OVERLAP
extern void boot_panel_finish(void);
extern void boot_panel_cancel(void);
#endif

static uint64_t ticks(void)
{
    uint64_t value;
    __asm__ volatile("mrrc p15,0,%Q0,%R0,c14" : "=r"(value));
    return value;
}

int boot_panel_performance_entry(unsigned millivolts)
{
    volatile uint32_t *words = (volatile uint32_t *)LOG;
    for (unsigned i = 0; i < sizeof(*LOG)/4; i++) words[i] = 0;
    LOG->magic = 0xa523b501U;
    LOG->version = 1;
    int result = original_panel_voltage(millivolts);
    LOG->voltage_result = result;
    LOG->entered_ticks = ticks();
    if (!result) {
        LOG->boost_attempted = 1;
        original_cpu_boost();
        LOG->boosted_ticks = ticks();
    }
    return result;
}

int boot_logo_speed_card_init(void)
{
    LOG->trained_ticks = ticks();
#ifdef TZX_PANEL_OVERLAP
    boot_panel_finish();
#endif
    return original_card_init();
}

void boot_logo_speed_return_cleanup(void)
{
    if (LOG->magic == 0xa523b501U && LOG->version == 1 && LOG->boost_attempted)
        original_cpu_restore();
#ifdef TZX_PANEL_OVERLAP
    boot_panel_cancel();
#endif
    LOG->returned_ticks = ticks();
}

/* The outer dram_probe frame holds exactly r4-r8 and LR. This also restores
 * CPU state when DRAM training fails before chain_load can run its cleanup.
 */
__attribute__((naked)) void boot_logo_speed_outer_return(void)
{
    __asm__ volatile("push {r0-r3,r12,lr}\n"
                     "bl boot_logo_speed_return_cleanup\n"
                     "pop {r0-r3,r12,lr}\n"
                     "pop {r4-r8,pc}");
}
