"""Add an opt-in exact-board HS200/HS400 path; normal boot remains DDR52."""
from pathlib import Path
import shutil

root=Path(__file__).resolve().parents[1]
source=Path('/opt/a523-debian-20261109/linux-hs-source')
host=source/'drivers/mmc/host/sunxi-mmc.c';core=source/'drivers/mmc/core/mmc.c'
text=host.read_text();assert 'tzx_emmc_host.inc' not in text
text=text.replace('#include <linux/spinlock.h>','#include <linux/spinlock.h>\n#include "../core/core.h"\n#include "../core/host.h"\n#include "../core/mmc_ops.h"\n#include "../core/tzx_emmc_hs.h"')
text=text.replace('#include "../core/tzx_emmc_hs.h"','#include "../core/tzx_emmc_hs.h"\n#include <linux/timer.h>\nstatic unsigned int tzx_hs_stage,tzx_hs_command;\nmodule_param(tzx_hs_stage,uint,0444);\nmodule_param(tzx_hs_command,uint,0444);')
old='\tbool\t\tuse_new_timings;\n};'
assert old in text
text=text.replace(old,'\tbool\t\tuse_new_timings;\n\tbool tzx_fast, tzx_tuning, tzx_transition;\n\tu8 tzx_sample, tzx_ds;\n\tu8 *tzx_ext_csd;\n\tu32 tzx_saved[5];\n\tstruct timer_list tzx_timer;\n\tunsigned long tzx_deadline;\n};')
old='\t\trval |= SDXC_2X_TIMING_MODE;'
assert text.count(old)==1
text=text.replace(old,'\t\tif (host->tzx_fast) rval &= ~SDXC_2X_TIMING_MODE;\n\t\telse rval |= SDXC_2X_TIMING_MODE;')
old='\tret = sunxi_mmc_calibrate(host, SDXC_REG_SAMP_DL_REG);'
new='''\tif (host->tzx_fast) {
        bool hs400=ios->timing==MMC_TIMING_MMC_HS400;
        bool fast=hs400 || ios->timing==MMC_TIMING_MMC_HS200;
        u32 drive=mmc_readl(host,REG_DRV_DL)&~(BIT(16)|BIT(17));
        drive|=BIT(16);
        if(ios->timing==MMC_TIMING_MMC_DDR52)drive|=BIT(17);
        mmc_writel(host,REG_DRV_DL,drive);
        writel((readl(host->reg_base+0x10c)&~BIT(31))|(hs400?BIT(31):0),host->reg_base+0x10c);
        writel((readl(host->reg_base+0x54)&~0xf)|(hs400?6:3),host->reg_base+0x54);
        writel(SDXC_CAL_DL_SW_EN|(fast?host->tzx_sample:0),host->reg_base+SDXC_REG_SAMP_DL_REG);
        writel(SDXC_CAL_DL_SW_EN|(hs400?host->tzx_ds:0),host->reg_base+SDXC_REG_DS_DL_REG);
        ret=0;
    } else ret = sunxi_mmc_calibrate(host, SDXC_REG_SAMP_DL_REG);'''
assert text.count(old)==1;text=text.replace(old,new)
old='static const struct mmc_host_ops sunxi_mmc_ops = {'
assert text.count(old)==1
text=text.replace(old,'#include "tzx_emmc_host.inc"\n\n'+old)
text=text.replace('\t.card_busy\t = sunxi_mmc_card_busy,','\t.card_busy\t = sunxi_mmc_card_busy,\n\t.execute_tuning = sunxi_mmc_tzx_tuning,\n\t.execute_hs400_tuning = sunxi_mmc_tzx_ds_tuning,')
# CMD21 has no multi-block data state to stop. A bad tap is an expected
# tuning result; normal data errors still follow the original recovery path.
old='\t\t\thost->manual_stop_mrq = mrq;'
assert text.count(old)==1
text=text.replace(old,'\t\t\tif (!(host->tzx_tuning && (mrq->cmd->opcode==MMC_SEND_TUNING_BLOCK_HS200 || mrq->cmd->opcode==MMC_SEND_EXT_CSD)))\n\t\t\t\thost->manual_stop_mrq = mrq;')
old='\t\tsunxi_mmc_dump_errinfo(host);'
assert text.count(old)==1
text=text.replace(old,'''\t\tif (host->int_sum & SDXC_RESP_TIMEOUT)
            mmc_debugfs_err_stats_inc(host->mmc,MMC_ERR_CMD_TIMEOUT);
        if (host->int_sum & SDXC_RESP_CRC_ERROR)
            mmc_debugfs_err_stats_inc(host->mmc,MMC_ERR_CMD_CRC);
        if (host->int_sum & SDXC_DATA_TIMEOUT)
            mmc_debugfs_err_stats_inc(host->mmc,MMC_ERR_DAT_TIMEOUT);
        if (host->int_sum & SDXC_DATA_CRC_ERROR)
            mmc_debugfs_err_stats_inc(host->mmc,MMC_ERR_DAT_CRC);
        if (host->int_sum & (SDXC_FIFO_RUN_ERROR|SDXC_HARD_WARE_LOCKED|SDXC_START_BIT_ERROR|SDXC_END_BIT_ERROR|SDXC_RESP_ERROR))
            mmc_debugfs_err_stats_inc(host->mmc,MMC_ERR_UNEXPECTED_IRQ);
'''+old)
text=text.replace('\thost->mrq = NULL;','\ttimer_delete(&host->tzx_timer);\n\thost->mrq = NULL;')
text=text.replace('\thost->mrq = mrq;','''\thost->mrq = mrq;
    if(host->tzx_tuning || host->tzx_transition) {
        tzx_hs_command=mrq->cmd->opcode;
        host->tzx_deadline=jiffies+msecs_to_jiffies(host->tzx_tuning?250:2000);
        mod_timer(&host->tzx_timer,host->tzx_deadline);
    }''')
text=text.replace('\thost->mmc = mmc;','\thost->mmc = mmc;\n\ttimer_setup(&host->tzx_timer,tzx_mmc_tuning_timeout,0);')
text=text.replace('\tmmc_remove_host(mmc);','\tmmc_remove_host(mmc);\n\ttimer_delete_sync(&host->tzx_timer);')
host.write_text(text)
text=core.read_text();assert 'tzx_emmc_core.inc' not in text
marker='static int mmc_init_card(struct mmc_host *host, u32 ocr,'
assert text.count(marker)==1
text=text.replace(marker,'#include "tzx_emmc_hs.h"\n#include "tzx_emmc_core.inc"\n\n'+marker)
core.write_text(text)
for name,dest in [('tzx_emmc_core.inc',core.parent),('tzx_emmc_hs.h',core.parent),('tzx_emmc_host.inc',host.parent)]:
    shutil.copyfile(root/'firmware'/name,dest/name)
print('OPT_IN_HS200_HS400_KERNEL_PREPARED')
