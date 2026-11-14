/* SPDX-License-Identifier: GPL-2.0-only */
/* A523 v4p6-compatible 1x sampling: 64 software delay taps. Sources and
 * register semantics: pinned Allwinner BSP sunxi-mmc-v4p5x.c. */
static int tzx_mmc_best_tap(u64 good)
{
    unsigned int i,start=0,length=0,best_start=0,best_length=0;
    for(i=0;i<64;i++) {
        if(good&BIT_ULL(i)) {
            if(!length)start=i;
            length++;
            if(length>best_length){best_start=start;best_length=length;}
        }else length=0;
    }
    return best_length>=8?best_start+(best_length-1)/2:-EIO;
}

/* A bad sampling tap may suppress COMMAND_DONE after RESPONSE_TIMEOUT.
 * Complete the tuning request through the normal IRQ cleanup path instead
 * of leaving the root device claimed indefinitely. No timer is armed for
 * ordinary root-filesystem I/O or for the unchanged normal boot path. */
static void tzx_mmc_tuning_timeout(struct timer_list *timer)
{
    struct sunxi_mmc_host *host=timer_container_of(host,timer,tzx_timer);
    struct mmc_request *mrq=NULL;
    unsigned long flags;
    irqreturn_t ret=IRQ_HANDLED;
    spin_lock_irqsave(&host->lock,flags);
    if((host->tzx_tuning || host->tzx_transition) && host->mrq && time_after_eq(jiffies,host->tzx_deadline)) {
        mrq=host->mrq;
        host->int_sum|=SDXC_DATA_TIMEOUT|SDXC_COMMAND_DONE;
        ret=sunxi_mmc_finalize_request(host);
        tzx_hs_stage=900000+mrq->cmd->opcode;
    }
    spin_unlock_irqrestore(&host->lock,flags);
    if(mrq) {
        if(ret==IRQ_HANDLED)mmc_request_done(host->mmc,mrq);
        else irq_wake_thread(host->irq,host);
    }
}

static int tzx_mmc_set_tap(struct sunxi_mmc_host *host,int reg,u8 tap)
{
    int ret=0;
    /* The CMD21 sampling path needs the clock latch used by the verified
     * HS200 profile. HS400 DS changes follow the BSP raw-delay path. */
    if(reg==SDXC_REG_SAMP_DL_REG) {
        ret=sunxi_mmc_oclk_onoff(host,0);
        if(ret)return ret;
    }
    writel(SDXC_CAL_DL_SW_EN|tap,host->reg_base+reg);
    readl(host->reg_base+reg);
    if(reg==SDXC_REG_SAMP_DL_REG)ret=sunxi_mmc_oclk_onoff(host,1);
    return ret;
}

static int sunxi_mmc_tzx_tuning(struct mmc_host *mmc,u32 opcode)
{
    struct sunxi_mmc_host *host=mmc_priv(mmc);
    u64 good=0;
    unsigned int tap,repeat;
    unsigned long deadline=jiffies+30*HZ;
    int ret=-EIO,best;
    u8 original=host->tzx_sample;
    if(!host->tzx_fast || opcode!=MMC_SEND_TUNING_BLOCK_HS200 ||
       mmc->ios.bus_width!=MMC_BUS_WIDTH_8)return -EOPNOTSUPP;
    host->tzx_tuning=true;
    for(tap=0;tap<64 && time_before(jiffies,deadline);tap++) {
        tzx_hs_stage=200000+tap;
        ret=tzx_mmc_set_tap(host,SDXC_REG_SAMP_DL_REG,tap);
        if(ret)goto out;
        for(repeat=0;repeat<3;repeat++)if(mmc_send_tuning(mmc,opcode,NULL))break;
        if(repeat==3)good|=BIT_ULL(tap);
        cond_resched();
    }
    best=tzx_mmc_best_tap(good);
    if(tap!=64 || best<0){ret=-EIO;goto out;}
    ret=tzx_mmc_set_tap(host,SDXC_REG_SAMP_DL_REG,best);if(ret)goto out;
    for(repeat=0;repeat<16;repeat++)if(mmc_send_tuning(mmc,opcode,NULL))break;
    if(repeat!=16){ret=-EIO;goto out;}
    host->tzx_sample=best;
    ret=0;
out:
    host->tzx_tuning=false;
    if(ret)tzx_mmc_set_tap(host,SDXC_REG_SAMP_DL_REG,original);
    dev_info(mmc_dev(mmc),"TZX HS200 %u Hz taps %016llx selected %u result %d\n",
             mmc->actual_clock,good,host->tzx_sample,ret);
    return ret;
}

static bool tzx_mmc_ext_csd_equal(const u8 *a,const u8 *b)
{
    unsigned int i;
    for(i=0;i<512;i++)
        if(i!=EXT_CSD_BUS_WIDTH && i!=EXT_CSD_HS_TIMING && a[i]!=b[i])return false;
    return true;
}

static int tzx_mmc_read_ext_csd(struct mmc_card *card,u8 *data)
{
    u8 *temporary=NULL;
    int ret=mmc_get_ext_csd(card,&temporary);
    if(!ret)memcpy(data,temporary,512);
    kfree(temporary);
    return ret;
}

static int sunxi_mmc_tzx_ds_tuning(struct mmc_host *mmc,struct mmc_card *card)
{
    struct sunxi_mmc_host *host=mmc_priv(mmc);
    u8 *data;
    u64 good=0;
    unsigned int tap,repeat;
    unsigned long deadline=jiffies+40*HZ;
    int ret=-EIO,best;
    if(!host->tzx_fast || !host->tzx_ext_csd)return -EOPNOTSUPP;
    data=kmalloc(512,GFP_KERNEL);if(!data)return -ENOMEM;
    host->tzx_tuning=true;
    for(tap=0;tap<64 && time_before(jiffies,deadline);tap++) {
        tzx_hs_stage=400000+tap;
        ret=tzx_mmc_set_tap(host,SDXC_REG_DS_DL_REG,tap);if(ret)goto out;
        for(repeat=0;repeat<3;repeat++) {
            ret=tzx_mmc_read_ext_csd(card,data);
            if(ret || !tzx_mmc_ext_csd_equal(data,host->tzx_ext_csd))break;
        }
        if(repeat==3)good|=BIT_ULL(tap);
        cond_resched();
    }
    best=tzx_mmc_best_tap(good);
    if(tap!=64 || best<0){ret=-EIO;goto out;}
    ret=tzx_mmc_set_tap(host,SDXC_REG_DS_DL_REG,best);if(ret)goto out;
    for(repeat=0;repeat<16;repeat++) {
        ret=tzx_mmc_read_ext_csd(card,data);
        if(ret || !tzx_mmc_ext_csd_equal(data,host->tzx_ext_csd)){ret=-EIO;goto out;}
    }
    host->tzx_ds=best;ret=0;
out:
    host->tzx_tuning=false;
    if(ret)tzx_mmc_set_tap(host,SDXC_REG_DS_DL_REG,host->tzx_ds);
    dev_info(mmc_dev(mmc),"TZX HS400 %u Hz DS taps %016llx selected %u result %d\n",
             mmc->actual_clock,good,host->tzx_ds,ret);
    kfree(data);return ret;
}

int sunxi_mmc_tzx_mode(struct mmc_host *mmc,unsigned int mode,unsigned int clock)
{
    static const u32 cid[]={0x3e01ff55,0x454d2020,0x20102091,0x70281b59};
    struct sunxi_mmc_host *host;
    struct mmc_card *card;
    int ret=-EPERM,rollback;
    unsigned int available;
    if(!of_machine_is_compatible("tzx,p30a523") ||
       !mmc->parent->of_node ||
       !of_device_is_compatible(mmc->parent->of_node,"allwinner,sun55i-a523-mmc") ||
       (mode!=0 && mode!=200 && mode!=400) || clock<25000000 || clock>100000000)
        return -EINVAL;
    host=mmc_priv(mmc);
    tzx_hs_stage=1;
    mmc_claim_host(mmc);
    card=mmc->card;
    if(!card || !mmc_card_mmc(card) || card->ext_csd.sectors!=244318208 ||
       memcmp(card->raw_cid,cid,sizeof(cid)) || !host->use_new_timings ||
       mmc->ios.bus_width!=MMC_BUS_WIDTH_8 || mmc->ios.signal_voltage!=MMC_SIGNAL_VOLTAGE_180)
        goto out;
    if(mode && !(card->ext_csd.raw_card_type & (mode==200?EXT_CSD_CARD_TYPE_HS200_1_8V:EXT_CSD_CARD_TYPE_HS400_1_8V)))
        goto out;
    if(!host->tzx_fast && mmc->ios.timing!=MMC_TIMING_MMC_DDR52)goto out;
    available=card->mmc_avail_type;
    if(!host->tzx_fast) {
        host->tzx_saved[0]=mmc_readl(host,REG_DRV_DL);
        host->tzx_saved[1]=mmc_readl(host,REG_SD_NTSR);
        host->tzx_saved[2]=readl(host->reg_base+SDXC_REG_DS_DL_REG);
        host->tzx_saved[3]=readl(host->reg_base+0x10c);
        host->tzx_saved[4]=readl(host->reg_base+0x54);
    }
    if(mode) {
        ret=mmc_get_ext_csd(card,&host->tzx_ext_csd);if(ret)goto out;
    }
    host->tzx_transition=true;
    /* First enter the 1x method at 25MHz, with no request in flight. */
    mmc_set_clock(mmc,25000000);
    host->tzx_fast=true;
    host->tzx_sample=0;host->tzx_ds=0;
    mmc->ops->set_ios(mmc,&mmc->ios);
    ret=mmc_tzx_switch_mode(card,mode,clock);
    tzx_hs_stage=ret?800001:2;
    if(ret) {
        rollback=mmc_tzx_switch_mode(card,0,25000000);
        if(rollback){dev_err(mmc_dev(mmc),"TZX rollback failed %d\n",rollback);ret=rollback;}
    }
    if(!mode || ret) {
        if(mmc->ios.timing==MMC_TIMING_MMC_DDR52 && mmc->actual_clock==25000000) {
            mmc_set_clock(mmc,0);
            mmc_writel(host,REG_DRV_DL,host->tzx_saved[0]);
            mmc_writel(host,REG_SD_NTSR,host->tzx_saved[1]);
            writel(host->tzx_saved[2],host->reg_base+SDXC_REG_DS_DL_REG);
            writel(host->tzx_saved[3],host->reg_base+0x10c);
            writel(host->tzx_saved[4],host->reg_base+0x54);
            host->tzx_fast=false;
            mmc_set_clock(mmc,25000000);
        }
        card->mmc_avail_type=available&~(EXT_CSD_CARD_TYPE_HS200|EXT_CSD_CARD_TYPE_HS400);
    }
    kfree(host->tzx_ext_csd);host->tzx_ext_csd=NULL;
    mmc_retune_disable(mmc);
out:
    host->tzx_transition=false;
    mmc_release_host(mmc);
    tzx_hs_stage=ret?800002:0;
    return ret;
}
EXPORT_SYMBOL_GPL(sunxi_mmc_tzx_mode);
