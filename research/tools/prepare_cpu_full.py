"""Extend the tested DCDC1 path only for this tablet's verified vf0300 bin."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
text = (root/'build/cpu-dvfs/source/tzx_cpufreq_dvfs.c').read_text()

def change(before, after, count=1):
    global text
    assert text.count(before) == count, (before, text.count(before))
    text = text.replace(before, after)

change('#include <linux/of.h>', '#include <linux/of.h>\n#include <linux/nvmem-consumer.h>\n#include <linux/topology.h>\nextern void tzx_topology_refresh_capacity(void);')
change('static unsigned long saved_frequency_ref[8];', '''static unsigned long saved_frequency_ref[8], saved_capacity[8];
static unsigned int sid_dvfs_word, vf_index=0x0300;
module_param(sid_dvfs_word,uint,0444);
module_param(vf_index,uint,0444);
/* BSP V0.71: 0x48 >> 4 = combi 4 -> vf0300. Its 1992 MHz OPP is zero.
 * Read only the public DVFS word through the nvmem provider; never write SID. */
static int check_speed_bin(void)
{
    struct nvmem_device *sid=nvmem_device_find("sunxi-sid0",device_match_name);
    __le32 word;
    unsigned int combi;
    int ret;
    if(IS_ERR(sid))return PTR_ERR(sid);
    ret=nvmem_device_read(sid,0x48,sizeof(word),&word);
    nvmem_device_put(sid);
    if(ret!=sizeof(word))return ret<0?ret:-EIO;
    sid_dvfs_word=le32_to_cpu(word);
    combi=(sid_dvfs_word>>12)&0xff;
    if(!combi)combi=(sid_dvfs_word>>4)&0xff;
    return combi==0x04 ? 0 : -ENODEV;
}''')
change('(cluster ? 1000 : 1150)', '1150')
change('(cluster ? 50 : 65)', '65')
change('''    } else {
        if (khz > 1344000) return 1000;''','''    } else {
        if (khz > 1680000) return 1150;
        if (khz > 1584000) return 1100;
        if (khz > 1488000) return 1050;
        if (khz > 1344000) return 1000;''')
change('i ? 1488000 : 1416000', 'i ? 1800000 : 1416000')
change('''    {.driver_data=(62 << 2) | 0, .frequency=1488000},''','''    {.driver_data=(62 << 2) | 0, .frequency=1488000},
    {.driver_data=(66 << 2) | 0, .frequency=1584000},
    {.driver_data=(70 << 2) | 0, .frequency=1680000},
    {.driver_data=(75 << 2) | 0, .frequency=1800000},''')
change('(n == 50 || n == 56 || n == 62)', '(n == 50 || n == 56 || n == 62 || n == 66 || n == 70 || n == 75)')
change('first ? 1488000 : 1416000', 'first ? 1800000 : 1416000')
change('''        WRITE_ONCE(per_cpu(capacity_freq_ref, cpu), first ? 1800000 : 1416000);''','''        WRITE_ONCE(per_cpu(capacity_freq_ref, cpu), first ? 1800000 : 1416000);
        /* Same normalization as arch_topology: BSP DMIPS/MHz * max kHz.
         * cpu_scale is the kernel's exported capacity interface. A queued
         * topology refresh follows driver registration, outside its locks. */
        WRITE_ONCE(per_cpu(cpu_scale, cpu), first ? 1024 : 922UL*1416000/1800000);''')
change('policy->cpuinfo.transition_latency = 1000000;', '''/* 25 x 10mV steps plus I2C/readback/settling. Avoid flooding the
     * sleepable slow-switch path with a fictitious 1ms transition budget. */
    policy->cpuinfo.transition_latency = 12000000;''')
change('.name = "tzx-a523-dvfs",', '.name = "tzx-a523-dvfs2",')
change('''    for (i = 0; i < 8; i++)
        saved_frequency_ref[i] = READ_ONCE(per_cpu(capacity_freq_ref, i));''','''    ret=check_speed_bin();
    if(ret)return ret;
    for (i = 0; i < 8; i++) {
        saved_frequency_ref[i] = READ_ONCE(per_cpu(capacity_freq_ref, i));
        saved_capacity[i] = READ_ONCE(per_cpu(cpu_scale,i));
    }''')
change('''        for (i = 0; i < 8; i++)
            WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);''','''        for (i = 0; i < 8; i++) {
            WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);
            WRITE_ONCE(per_cpu(cpu_scale,i),saved_capacity[i]);
        }''')
change('''    for (i = 0; i < 8; i++)
        WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);''','''    for (i = 0; i < 8; i++) {
        WRITE_ONCE(per_cpu(capacity_freq_ref, i), saved_frequency_ref[i]);
        WRITE_ONCE(per_cpu(cpu_scale,i),saved_capacity[i]);
    }''')
change('little 120..1416 big 120..1488 MHz', 'vf0300 little 120..1416 big 120..1800 MHz')
change('''    ready = true;
    INIT_DELAYED_WORK''','''    tzx_topology_refresh_capacity();
    ready = true;
    INIT_DELAYED_WORK''')
change('''    iounmap(regs);
    clk_disable_unprepare(bypass);
    clk_put(bypass);
}''','''    tzx_topology_refresh_capacity();
    iounmap(regs);
    clk_disable_unprepare(bypass);
    clk_put(bypass);
}''')
(root/'firmware/tzx_cpufreq_dvfs_v2.c').write_text(text, newline='\n')
cooling=(root/'build/cpu-dvfs/source/tzx_cpu_dvfs_cooling.c').read_text()
assert cooling.count('(i ? 1488000 : 1416000)') == 1
cooling=cooling.replace('(i ? 1488000 : 1416000)', '(i ? 1800000 : 1416000)')
needle='''\tif (trip->type != THERMAL_TRIP_PASSIVE || state < 1 || state > 2)
\t\treturn false;
\tif (cdev != clusters[0].cdev && cdev != clusters[1].cdev)
\t\treturn false;'''
assert cooling.count(needle)==1
cooling=cooling.replace(needle,'''\tif (trip->type != THERMAL_TRIP_PASSIVE)
\t\treturn false;
\tif (!strcmp(cdev->type,"devfreq-1800000.gpu") && (state==11 || state==13))
\t\tstate-=10; /* Native descending OPP states: 1=400, 3=200 MHz. */
\telse if ((cdev==clusters[0].cdev || cdev==clusters[1].cdev) && state>=1 && state<=2) { }
\telse return false;''')
needle='module_param(second_trip, int, 0444);'
assert cooling.count(needle)==1
cooling=cooling.replace(needle,needle+'''
static int gpu_first_trip=65000,gpu_second_trip=70000;
module_param(gpu_first_trip,int,0444);
module_param(gpu_second_trip,int,0444);''')
needle='''\tstruct thermal_trip trips[] = {'''
assert cooling.count(needle)==1
cooling=cooling.replace(needle,needle+'''
        { .temperature=gpu_first_trip, .hysteresis=5000,
          .type=THERMAL_TRIP_PASSIVE, .priv=THERMAL_INT_TO_TRIP_PRIV(11) },
        { .temperature=gpu_second_trip, .hysteresis=5000,
          .type=THERMAL_TRIP_PASSIVE, .priv=THERMAL_INT_TO_TRIP_PRIV(13) },''')
needle='''\tif (!of_machine_is_compatible("tzx,p30a523"))
\t\treturn -ENODEV;'''
assert cooling.count(needle)==1
cooling=cooling.replace(needle,needle+'''
    if(gpu_first_trip<30000 || gpu_first_trip>65000 ||
       gpu_second_trip<=gpu_first_trip || gpu_second_trip>70000)return -EINVAL;''')
(root/'firmware/tzx_cpu_dvfs_cooling_v2.c').write_text(cooling, newline='\n')
print('VF0300_1800MHZ_DRIVER_AND_NORMALIZED_CAPACITY_PREPARED')
