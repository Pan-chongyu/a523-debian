"""Generate an independent voltage-aware driver from the qualified PLL path."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root/'build/cpu-dvfs/source'
out.mkdir(parents=True, exist_ok=True)
text = (root/'firmware/tzx_cpufreq_safepll.c').read_text()
def replace(before, after):
    global text
    assert text.count(before) == 1, before
    text = text.replace(before, after)

replace('#include <linux/io.h>', '#include <linux/io.h>\n#include <linux/i2c.h>\n#include <linux/jiffies.h>\n#include <linux/pm_qos.h>\n#include <linux/workqueue.h>')
replace('static struct clk *bypass;', '''static struct clk *bypass;
static struct i2c_adapter *pmic;
static const u16 pmic_address[] = {0x34, 0x36};
static const u8 voltage_register[] = {0x83, 0x13};
static u8 initial_voltage[2];
static unsigned int rail_mv[2] = {900, 900};
module_param_array(rail_mv, uint, NULL, 0444);
static struct cpufreq_policy *lease_policy[2];
static struct freq_qos_request lease_qos[2];
static struct delayed_work lease_work;
static unsigned long lease_deadline;
static unsigned int lease_seconds = 30, lease_active;
static bool stopping, ready;
module_param(lease_seconds, uint, 0444);
module_param(lease_active, uint, 0444);

static int pmic_read(unsigned int cluster, u8 reg, u8 *value)
{
    struct i2c_msg messages[] = {
        {.addr=pmic_address[cluster], .len=1, .buf=&reg},
        {.addr=pmic_address[cluster], .flags=I2C_M_RD, .len=1, .buf=value},
    };
    int ret = i2c_transfer(pmic, messages, 2);
    return ret == 2 ? 0 : ret < 0 ? ret : -EIO;
}

/* Both identified DCDC1 selectors are 500mV + 10mV*n in this range.
 * Only 0x34:0x83 and 0x36:0x13 are writable here. DVM bit 7 is preserved.
 * CPU clocks are never raised before readback and the settling interval. */
static int set_voltage(unsigned int cluster, unsigned int millivolts)
{
    u8 observed, wanted, pair[2], step;
    struct i2c_msg message = {.addr=pmic_address[cluster], .len=2, .buf=pair};
    int ret;
    if (millivolts < 900 || millivolts > (cluster ? 1000 : 1150) || millivolts % 10)
        return -EINVAL;
    ret = pmic_read(cluster, voltage_register[cluster], &observed);
    if (ret)
        return ret;
    if ((observed & 0x80) != (initial_voltage[cluster] & 0x80) ||
        (observed & 0x7f) < 40 || (observed & 0x7f) > (cluster ? 50 : 65))
        return -EPERM;
    wanted = (millivolts - 500) / 10;
    while ((observed & 0x7f) != wanted) {
        step = observed + ((observed & 0x7f) < wanted ? 1 : -1);
        pair[0] = voltage_register[cluster];
        pair[1] = step;
        ret = i2c_transfer(pmic, &message, 1);
        if (ret != 1)
            return ret < 0 ? ret : -EIO;
        usleep_range(200, 350);
        ret = pmic_read(cluster, voltage_register[cluster], &observed);
        if (ret || observed != step)
            return ret ? ret : -EIO;
        WRITE_ONCE(rail_mv[cluster], 500 + (observed & 0x7f) * 10);
    }
    usleep_range(500, 700);
    return 0;
}

static unsigned int required_mv(unsigned int cluster, unsigned int khz)
{
    if (!cluster) {
        if (khz > 1224000) return 1150;
        if (khz > 1008000) return 1050;
        if (khz > 792000) return 960;
    } else {
        if (khz > 1344000) return 1000;
        if (khz > 1200000) return 960;
        if (khz > 1008000) return 920;
    }
    return 900;
}

static int renew_set(const char *value, const struct kernel_param *param)
{
    unsigned int requested;
    int ret = kstrtouint(value, 0, &requested), i;
    if (ret || requested != 1)
        return -EINVAL;
    mutex_lock(&clock_lock);
    if (!ready || stopping || clock_fault) {
        mutex_unlock(&clock_lock);
        return -EIO;
    }
    lease_deadline = jiffies + lease_seconds * HZ;
    WRITE_ONCE(lease_active, 1);
    mutex_unlock(&clock_lock);
    for (i = 0; i < 2; i++)
        freq_qos_update_request(&lease_qos[i], i ? 1488000 : 1416000);
    return 0;
}
static const struct kernel_param_ops renew_ops = {.set=renew_set, .get=param_get_uint};
module_param_cb(renew, &renew_ops, &lease_active, 0600);

static void check_lease(struct work_struct *work)
{
    int i;
    bool expired;
    mutex_lock(&clock_lock);
    expired = clock_fault || time_after_eq(jiffies, lease_deadline);
    if (expired)
        WRITE_ONCE(lease_active, 0);
    mutex_unlock(&clock_lock);
    if (expired)
        for (i = 0; i < 2; i++)
            freq_qos_update_request(&lease_qos[i], 480000);
    if (!READ_ONCE(stopping))
        schedule_delayed_work(&lease_work, msecs_to_jiffies(200));
}''')
start = text.index('static struct cpufreq_frequency_table little[]')
end = text.index('static bool known(', start)
tables = ''
for name, frequencies in (('little', (120,240,480,600,792,1008,1224,1416)),
                          ('big', (120,240,480,600,792,1008,1200,1344,1488))):
    tables += 'static struct cpufreq_frequency_table '+name+'[] = {\n'
    for freq in frequencies:
        n, div = (20, 2) if freq == 120 else (20, 1) if freq == 240 else (freq//24, 0)
        tables += f'    {{.driver_data=({n} << 2) | {div}, .frequency={freq*1000}}},\n'
    tables += '    {.frequency=CPUFREQ_TABLE_END},\n};\n\n'
text = text[:start]+tables+text[end:]
replace('(n == 20 || n == 25 || n == 33 || (cluster && n == 42));',
        '(n == 20 || n == 25 || n == 33 || n == 42 ||\n            (!cluster && (n == 51 || n == 59)) ||\n            (cluster && (n == 50 || n == 56 || n == 62)));')
replace('unsigned int cluster = policy->cpu / 4, value;',
        'unsigned int cluster = policy->cpu / 4, value, millivolts;')
replace('    else\n        ret = select_clock(cluster, value >> 2, value & 3);', '''    else {
        millivolts = required_mv(cluster, policy->freq_table[index].frequency);
        if (policy->freq_table[index].frequency > 480000 &&
            (!lease_active || time_after_eq(jiffies, lease_deadline))) {
            ret = -EAGAIN;
            goto unlock;
        }
        ret = 0;
        if (millivolts > rail_mv[cluster])
            ret = set_voltage(cluster, millivolts);
        if (!ret)
            ret = select_clock(cluster, value >> 2, value & 3);
        if (!ret && millivolts < rail_mv[cluster])
            ret = set_voltage(cluster, millivolts);
    }''')
replace('    mutex_unlock(&clock_lock);\n    return ret;\n}\n\nstatic int policy_init',
        'unlock:\n    mutex_unlock(&clock_lock);\n    return ret;\n}\n\nstatic int policy_init')
replace('first ? 1008000 : 792000', 'first ? 1488000 : 1416000')
replace('.name = "tzx-a523-safepll"', '.name = "tzx-a523-dvfs"')
replace('            writel(saved_mux[i], regs + mux_offsets[i]);',
        '            writel(saved_mux[i], regs + mux_offsets[i]);\n            if (set_voltage(i, 900))\n                pr_err("tzx-dvfs: CPU%d 900mV restore failed\\n", i);')
replace('    ret = cpufreq_register_driver(&driver);', '''    pmic = i2c_get_adapter(0);
    if (!pmic) { ret = -ENODEV; goto unmap; }
    for (i = 0; i < 2; i++) {
        u8 id;
        ret = pmic_read(i, 3, &id);
        if (ret || id != (i ? 0x49 : 0xff)) { ret = -ENODEV; goto put_i2c; }
        ret = pmic_read(i, voltage_register[i], &initial_voltage[i]);
        if (ret || (initial_voltage[i] & 0x7f) != 40) { ret = -EPERM; goto put_i2c; }
    }
    if (lease_seconds < 3 || lease_seconds > 60) { ret = -EINVAL; goto put_i2c; }
    lease_deadline = jiffies;
    ret = cpufreq_register_driver(&driver);''')
replace('        goto unmap;\n    }\n    pr_info("tzx-safepll:', '        goto put_i2c;\n    }\n    for (i = 0; i < 2; i++) {\n        lease_policy[i] = cpufreq_cpu_get(i * 4);\n        ret = freq_qos_add_request(&lease_policy[i]->constraints, &lease_qos[i], FREQ_QOS_MAX, 480000);\n        if (ret < 0) goto remove_qos;\n    }\n    ready = true;\n    INIT_DELAYED_WORK(&lease_work, check_lease);\n    schedule_delayed_work(&lease_work, msecs_to_jiffies(200));\n    pr_info("tzx-dvfs:')
replace('fixed-voltage tables little 120..792, big 120..1008 MHz; initial limits 480 MHz',
        'DCDC1-only DVFS little 120..1416 big 120..1488 MHz; initial 480, renewable lease')
replace('unmap:\n    iounmap(regs);', '''remove_qos:
    while (i--) {
        freq_qos_remove_request(&lease_qos[i]);
        cpufreq_cpu_put(lease_policy[i]);
    }
    cpufreq_unregister_driver(&driver);
put_i2c:
    i2c_put_adapter(pmic);
unmap:
    iounmap(regs);''')
replace('    cpufreq_unregister_driver(&driver);\n    restore();', '''    WRITE_ONCE(stopping, true);
    cancel_delayed_work_sync(&lease_work);
    for (i = 0; i < 2; i++) {
        freq_qos_remove_request(&lease_qos[i]);
        cpufreq_cpu_put(lease_policy[i]);
    }
    cpufreq_unregister_driver(&driver);
    restore();
    i2c_put_adapter(pmic);''')
text = text.replace('/* A523 online CPU clock qualification at the existing 900 mV rails.',
                    '/* A523 voltage-aware CPU performance with bounded DCDC1 ramps.')
text = text.replace(' * No PMIC/DSU/DRAM/backup-PLL writes. Both policies initially capped 480 MHz.',
                    ' * Only CPU DCDC1 writes; no DSU/DRAM/backup-PLL writes. Initial cap 480 MHz.')
text = text.replace('A523 CPU PLL qualification within universal 900 mV OPP limits',
                    'A523 CPU DCDC1 DVFS with readback, settling, thermal policy and lease')
(out/'tzx_cpufreq_dvfs.c').write_text(text)
cooler = (root/'build/cpu-performance/source/tzx_cpu_perf_cooling.c').read_text()
assert cooler.count('i ? 1008000 : 792000') == 1
cooler = cooler.replace('i ? 1008000 : 792000', 'i ? 1488000 : 1416000')
(out/'tzx_cpu_dvfs_cooling.c').write_text(cooler)
print('CPU_DVFS_SOURCES_PREPARED')
