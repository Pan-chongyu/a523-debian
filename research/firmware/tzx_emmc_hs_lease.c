// SPDX-License-Identifier: GPL-2.0-only
/* Exact-CID profile control. The kernel owns card transitions and tuning;
 * this module owns a renewable lease and reverts on any subsequent I/O error. */
#include <linux/mmc/host.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of_platform.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/workqueue.h>
#include "core.h"
#include "tzx_emmc_hs.h"

static struct platform_device *device;
static struct mmc_host *host;
static DEFINE_MUTEX(lock);
static struct delayed_work monitor;
static unsigned long deadline;
static unsigned int mode, mhz=25, actual_hz, lease_seconds=30;
static int fault;
static bool ready,stopping;
static u32 baseline[MMC_ERR_MAX];
module_param(mode,uint,0444);
module_param(mhz,uint,0444);
module_param(actual_hz,uint,0444);
module_param(fault,int,0444);
module_param(lease_seconds,uint,0444);

static void snapshot(void)
{
    unsigned int i;
    for(i=0;i<MMC_ERR_MAX;i++)baseline[i]=READ_ONCE(host->err_stats[i]);
}

static int restore(void)
{
    int ret=sunxi_mmc_tzx_mode(host,0,25000000);
    actual_hz=host->actual_clock;
    if(!ret){mode=0;mhz=25;snapshot();}
    return ret;
}

static int profile_set(const char *value,const struct kernel_param *param)
{
    unsigned int new_mode,new_mhz;
    int ret;
    if(sscanf(value,"%u,%u",&new_mode,&new_mhz)!=2 ||
       (new_mode!=0 && new_mode!=200 && new_mode!=400) ||
       new_mhz<25 || new_mhz>200 || (!new_mode && new_mhz!=25))return -EINVAL;
    mutex_lock(&lock);
    if(!ready || stopping || (fault && new_mode)){ret=-EIO;goto out;}
    deadline=jiffies+lease_seconds*HZ;
    ret=sunxi_mmc_tzx_mode(host,new_mode,new_mhz*1000000);
    actual_hz=host->actual_clock;
    if(ret) {
        fault=ret;
        /* The core has already attempted protocol rollback. Retry at the
         * baseline while still excluding every concurrent profile change. */
        if(restore())pr_err("TZX eMMC lease: protocol restore failed\n");
    } else {
        mode=new_mode;mhz=new_mhz;snapshot();
        deadline=jiffies+lease_seconds*HZ;
    }
out:
    mutex_unlock(&lock);
    return ret;
}

static int profile_get(char *buffer,const struct kernel_param *param)
{
    return scnprintf(buffer,PAGE_SIZE,"%u,%u\n",mode,mhz);
}
static const struct kernel_param_ops profile_ops={.set=profile_set,.get=profile_get};
module_param_cb(profile,&profile_ops,NULL,0600);

static int renew_set(const char *value,const struct kernel_param *param)
{
    unsigned int n;int ret=kstrtouint(value,0,&n);
    if(ret || n!=1)return -EINVAL;
    mutex_lock(&lock);
    if(!ready || stopping || fault)ret=-EIO;
    else deadline=jiffies+lease_seconds*HZ;
    mutex_unlock(&lock);return ret;
}
static const struct kernel_param_ops renew_ops={.set=renew_set};
module_param_cb(renew,&renew_ops,NULL,0200);

static void check(struct work_struct *work)
{
    unsigned int i;
    mutex_lock(&lock);
    for(i=0;i<MMC_ERR_MAX;i++)
        if(READ_ONCE(host->err_stats[i])!=baseline[i])fault=-EIO;
    if(mode && (fault || time_after_eq(jiffies,deadline))) {
        if(restore())fault=-EIO;
    }
    if(!stopping)schedule_delayed_work(&monitor,msecs_to_jiffies(200));
    mutex_unlock(&lock);
}

static int __init start(void)
{
    static const u32 cid[]={0x3e01ff55,0x454d2020,0x20102091,0x70281b59};
    struct device_node *node;
    bool valid;
    if(!of_machine_is_compatible("tzx,p30a523") || lease_seconds<3 || lease_seconds>60)return -EINVAL;
    node=of_find_node_by_path("/soc/mmc@4022000");if(!node)return -ENODEV;
    device=of_find_device_by_node(node);of_node_put(node);if(!device)return -ENODEV;
    host=platform_get_drvdata(device);
    if(!host || strcmp(mmc_hostname(host),"mmc0"))goto fail;
    mmc_claim_host(host);
    valid=host->card && mmc_card_mmc(host->card) &&
        host->card->ext_csd.sectors==244318208 &&
        !memcmp(host->card->raw_cid,cid,sizeof(cid)) &&
        host->ios.timing==MMC_TIMING_MMC_DDR52 &&
        host->ios.bus_width==MMC_BUS_WIDTH_8 &&
        host->ios.signal_voltage==MMC_SIGNAL_VOLTAGE_180 &&
        host->f_max==25000000 && host->actual_clock==25000000;
    if(valid){snapshot();actual_hz=host->actual_clock;}
    mmc_release_host(host);if(!valid)goto fail;
    ready=true;deadline=jiffies;
    INIT_DELAYED_WORK(&monitor,check);schedule_delayed_work(&monitor,msecs_to_jiffies(200));
    pr_info("TZX eMMC HS lease: baseline DDR52/25MHz, renewable %us\n",lease_seconds);
    return 0;
fail:
    put_device(&device->dev);return -ENODEV;
}

static void __exit stop(void)
{
    mutex_lock(&lock);stopping=true;mutex_unlock(&lock);
    cancel_delayed_work_sync(&monitor);
    mutex_lock(&lock);
    if(mode && restore())pr_err("TZX eMMC lease: unload restore failed\n");
    mutex_unlock(&lock);put_device(&device->dev);
}
module_init(start);module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Leased exact-board HS200/HS400 profiles with protocol fallback");
