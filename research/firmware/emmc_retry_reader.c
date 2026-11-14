/* SPDX-License-Identifier: MIT */
/* Keep the sector reader used by the working base loader. Recover a reported
 * I/O error by resetting the card/controller and lowering only the clock. */
#define main unused_fel_entry
#define work unused_fel_work
#include "../upstream/A523-root/tools/fel-emmc.c"

static unsigned divider = 1; /* HOSC/(2*(1+1)) = 6 MHz, 1-bit SDR. */

static int exact_card_init(void) {
    unsigned cid[4];
    const unsigned expected[] = {0x70281b59,0x20102091,0x454d2020,0x3e01ff55};
    int result = emmc_init(cid);
    if (result) return result;
    for (unsigned i=0;i<4;i++) if (cid[i]!=expected[i]) return -9;
    writel(BIT(31)|divider,SMHC_CLKCR);
    if (smhc_update_clk()) return -20;
    writel(BIT(31)|BIT(16)|divider,SMHC_CLKCR);
    if (smhc_update_clk()) return -21;
    writel(BIT(16)|divider,SMHC_CLKCR);
    return smhc_update_clk();
}
int cold_emmc_init(void) { return exact_card_init(); }
int cold_emmc_slower(void) { divider=29; return exact_card_init(); }

int cold_emmc_read(unsigned sector,void *data) {
    int result=-1;
    for (unsigned attempt=0;attempt<3;attempt++) {
        writel(sector,RTC_GP(5));
        writel(attempt,RTC_GP(1));
        result=read_sector(sector,data);
        if (!result) return 0;
        writel((unsigned)result,RTC_GP(0));
        writel(readl(SMHC_RINT),RTC_GP(7));
        /* The watchdog is restarted during bounded recovery, as well as
         * after normal sector reads in the chain loader. */
        writel(0x14af,0x0205000c);
        divider=attempt?29:5; /* 2 MHz, then 400 kHz on repeated error. */
        if (exact_card_init()) return -22;
    }
    return result;
}
