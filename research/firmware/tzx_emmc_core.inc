/* SPDX-License-Identifier: GPL-2.0-only */
/* Called only by the exact-CID, claimed-host TZX sunxi extension. The
 * underlying transitions are the same ones used by normal MMC init/retune.
 * Clock/voltage/card configuration are restored before releasing the host. */
static int tzx_mmc_to_hs(struct mmc_card *card)
{
    struct mmc_host *host=card->host;
    int ret;
    mmc_retune_disable(host);
    mmc_set_clock(host,25000000);
    if (mmc_card_hs400(card)) {
        ret=__mmc_switch(card,EXT_CSD_CMD_SET_NORMAL,EXT_CSD_HS_TIMING,
            EXT_CSD_TIMING_HS,card->ext_csd.generic_cmd6_time,0,false,true,MMC_CMD_RETRIES);
        if(ret)return ret;
        mmc_set_timing(host,MMC_TIMING_MMC_DDR52);
        ret=mmc_switch_status(card,true);if(ret)return ret;
    } else if (mmc_card_hs200(card)) {
        ret=__mmc_switch(card,EXT_CSD_CMD_SET_NORMAL,EXT_CSD_HS_TIMING,
            EXT_CSD_TIMING_HS,card->ext_csd.generic_cmd6_time,0,false,true,MMC_CMD_RETRIES);
        if(ret)return ret;
        mmc_set_timing(host,MMC_TIMING_MMC_HS);
        ret=mmc_switch_status(card,true);if(ret)return ret;
    }
    if(mmc_card_ddr52(card)) {
        ret=__mmc_switch(card,EXT_CSD_CMD_SET_NORMAL,EXT_CSD_BUS_WIDTH,
            EXT_CSD_BUS_WIDTH_8,card->ext_csd.generic_cmd6_time,0,false,true,MMC_CMD_RETRIES);
        if(ret)return ret;
        mmc_set_timing(host,MMC_TIMING_MMC_HS);
        ret=mmc_switch_status(card,true);if(ret)return ret;
    }
    return host->ios.timing==MMC_TIMING_MMC_HS?0:-EINVAL;
}

int mmc_tzx_switch_mode(struct mmc_card *card,unsigned int mode,unsigned int clock)
{
    struct mmc_host *host=card->host;
    int ret=tzx_mmc_to_hs(card);
    if(ret)return ret;
    if(!mode) {
        host->f_max=25000000;
        ret=__mmc_switch(card,EXT_CSD_CMD_SET_NORMAL,EXT_CSD_BUS_WIDTH,
            EXT_CSD_DDR_BUS_WIDTH_8,card->ext_csd.generic_cmd6_time,0,false,true,MMC_CMD_RETRIES);
        if(ret)return ret;
        mmc_set_timing(host,MMC_TIMING_MMC_DDR52);
        mmc_set_clock(host,25000000);
        return mmc_switch_status(card,true);
    }
    host->f_max=clock;
    card->ext_csd.hs200_max_dtr=MMC_HS200_MAX_DTR;
    card->mmc_avail_type|=EXT_CSD_CARD_TYPE_HS200_1_8V;
    if(mode==400)card->mmc_avail_type|=EXT_CSD_CARD_TYPE_HS400_1_8V;
    else card->mmc_avail_type&=~EXT_CSD_CARD_TYPE_HS400;
    ret=mmc_select_hs200(card);if(ret)return ret;
    mmc_set_bus_speed(card);
    ret=mmc_hs200_tuning(card);if(ret)return ret;
    if(mode==400)ret=mmc_select_hs400(card);
    return ret;
}
