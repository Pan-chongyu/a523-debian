// SPDX-License-Identifier: GPL-2.0-only
/* Bound Panfrost's own governor using device frequency QoS. Never write clocks. */
#include <linux/clk.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/pm_qos.h>
#include <linux/thermal.h>
#include <linux/workqueue.h>

static struct device *gpu;
static struct clk *clock;
static void __iomem *ccu;
static struct dev_pm_qos_request cap;
static struct thermal_zone_device *sensors[5];
static const char * const names[]={"cpu-big-thermal","cpu-little-thermal",
    "gpu-thermal","npu-thermal","ddr-thermal"};
static DEFINE_MUTEX(lock);
static struct delayed_work work;
static unsigned long deadline;
static unsigned int lease_seconds=30, maximum_mhz=200, limit_mhz=200;
static unsigned int actual_mhz, transitions;
static int first_trip=65000, second_trip=70000, fault_trip=85000;
static int temperature_mc, peak_temperature_mc, fault_temperature_mc, fault;
static bool stopping, ready, qos_added;
module_param(lease_seconds,uint,0444);
module_param(first_trip,int,0444);
module_param(second_trip,int,0444);
module_param(fault_trip,int,0444);
module_param(actual_mhz,uint,0444);
module_param(limit_mhz,uint,0444);
module_param(transitions,uint,0444);
module_param(temperature_mc,int,0444);
module_param(peak_temperature_mc,int,0444);
module_param(fault_temperature_mc,int,0444);
module_param(fault,int,0444);

static int update(void)
{
    static const unsigned long parent[]={0,0,600000000,400000000,300000000,200000000};
    unsigned int target=200, mhz, mux;
    unsigned long rate;
    int i,value,ret=0,highest=0;
    u32 reg;
    for(i=0;i<ARRAY_SIZE(sensors);i++) {
        ret=thermal_zone_get_temp(sensors[i],&value);
        if(ret || value<=0 || value>125000) {fault=ret?ret:-ENODATA;break;}
        highest=max(highest,value);
    }
    temperature_mc=highest;
    peak_temperature_mc=max(peak_temperature_mc,highest);
    /* Valid hot readings engage the 65/70C cooling caps. Reserve a sticky
     * fault for the same 85C emergency boundary as the CPU supervisor. */
    if(highest>=fault_trip && !fault) {
        fault_temperature_mc=highest;fault=-EOVERFLOW;
        pr_err("tzx-gpu-devfreq: emergency thermal latch at %d mC\n",highest);
    }
    if(!fault && time_before(jiffies,deadline)) {
        target=maximum_mhz;
        if(highest>=second_trip)target=200;
        else if(highest>=first_trip)target=min(target,400U);
    }
    if(qos_added && target!=limit_mhz) {
        ret=dev_pm_qos_update_request(&cap,target*1000);
        if(ret<0)fault=ret;
        else limit_mhz=target;
    }
    rate=clk_get_rate(clock);mhz=rate/1000000;
    reg=readl(ccu+0x670);mux=(reg>>24)&7;
    /* CCU cached rate and register reads can straddle a governor change.
     * A subsequent monitor iteration verifies the stable state. */
    if(mhz!=actual_mhz) {actual_mhz=mhz;transitions++;}
    if(mux<2 || mux>5 || !parent[mux] ||
       (mhz!=150 && mhz!=200 && mhz!=300 && mhz!=400 && mhz!=600))fault=-EIO;
    if(fault && qos_added && limit_mhz!=200) {
        dev_pm_qos_update_request(&cap,200000);limit_mhz=200;
    }
    return fault;
}
static int request(const char *value,const struct kernel_param *unused)
{
    unsigned int target;
    int ret=kstrtouint(value,0,&target);
    if(ret || (target!=200 && target!=300 && target!=400 && target!=600))return -EINVAL;
    mutex_lock(&lock);
    if(!ready || stopping || (fault && target!=200))ret=-EIO;
    else {
        maximum_mhz=target;deadline=jiffies+lease_seconds*HZ;
        ret=update();
        /* Cleanup must still be able to acknowledge a successfully applied
         * conservative cap after a latched fault. The fault stays visible. */
        if(target==200 && limit_mhz==200)ret=0;
    }
    mutex_unlock(&lock);
    return ret;
}
static const struct kernel_param_ops request_ops={.set=request,.get=param_get_uint};
module_param_cb(maximum_mhz,&request_ops,&maximum_mhz,0600);
static void tick(struct work_struct *unused)
{
    mutex_lock(&lock);
    update();
    if(!stopping)schedule_delayed_work(&work,msecs_to_jiffies(100));
    mutex_unlock(&lock);
}
static void cleanup(void)
{
    int i;
    if(qos_added)dev_pm_qos_remove_request(&cap);
    if(clock)clk_put(clock);
    if(ccu)iounmap(ccu);
    for(i=0;i<ARRAY_SIZE(sensors);i++)if(sensors[i])put_device(thermal_zone_device(sensors[i]));
    if(gpu)put_device(gpu);
}
static int __init start(void)
{
    struct device_node *node;
    struct platform_device *device;
    int i,ret;
    if(!of_machine_is_compatible("tzx,p30a523") || lease_seconds<3 || lease_seconds>60 ||
       first_trip<30000 || first_trip>65000 || second_trip<=first_trip || second_trip>70000 ||
       fault_trip<30000 || fault_trip>85000)return -EINVAL;
    node=of_find_node_by_path("/soc/gpu@1800000");
    if(!node)return -ENODEV;
    device=of_find_device_by_node(node);of_node_put(node);
    if(!device)return -ENODEV;
    gpu=&device->dev;
    if(!gpu->driver) {ret=-ENODEV;goto fail;}
    clock=clk_get(gpu,NULL);
    if(IS_ERR(clock)) {ret=PTR_ERR(clock);clock=NULL;goto fail;}
    ccu=ioremap(0x02001000,0x1000);
    if(!ccu) {ret=-ENOMEM;goto fail;}
    for(i=0;i<ARRAY_SIZE(sensors);i++) {
        sensors[i]=thermal_zone_get_zone_by_name(names[i]);
        if(IS_ERR(sensors[i])) {ret=PTR_ERR(sensors[i]);sensors[i]=NULL;goto fail;}
        get_device(thermal_zone_device(sensors[i]));
    }
    ret=dev_pm_qos_add_request(gpu,&cap,DEV_PM_QOS_MAX_FREQUENCY,200000);
    if(ret<0)goto fail;
    qos_added=true;ready=true;
    if(update()) {ret=fault;goto fail;}
    INIT_DELAYED_WORK(&work,tick);schedule_delayed_work(&work,msecs_to_jiffies(100));
    pr_info("tzx-gpu-devfreq: native governor QoS guard; baseline max200, 30s lease, thermal65/70C\n");
    return 0;
fail:
    cleanup();return ret;
}
static void __exit stop(void)
{
    mutex_lock(&lock);stopping=true;ready=false;mutex_unlock(&lock);
    cancel_delayed_work_sync(&work);cleanup();
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Native Panfrost devfreq maximum QoS, thermal and expiring-lease guard");
