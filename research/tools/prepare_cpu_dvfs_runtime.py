"""Keep the established ownership/rollback rules for the qualified DVFS driver."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
text=(root/'firmware/tzx_cpu_performance_runtime.py').read_text()
text=text.replace('tzx-cpu-performance','tzx-cpu-dvfs').replace('cpu-performance-','cpu-dvfs-')
text=text.replace('tzx_cpu_perf_cooling','tzx_cpu_dvfs_cooling').replace('tzx_cpufreq_safepll','tzx_cpufreq_dvfs')
text=text.replace('792000, 1008000','1416000, 1488000').replace('tzx-a523-safepll','tzx-a523-dvfs')
text=text.replace("'voltage_changed': False", "'voltage_changed': True, 'CPU_DCDC1_only': True")
text=text.replace("    run('systemctl', 'stop', 'tzx-cpu-cooling.service')", """    run('systemctl', 'stop', 'tzx-cpu-performance.service')
    run('systemctl', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service')
    run('systemctl', 'stop', 'tzx-cpu-cooling.service')""")
text=text.replace("    run('insmod', str(ROOT/'tzx_cpufreq_dvfs.ko'))", """    run('insmod', str(ROOT/'tzx_cpufreq_dvfs.ko'))
    Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').write_text('1')""")
text=text.replace("        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096", """        Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').write_text('1')
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096""")
text=text.replace("            assert all(observed[k] == voltage[k] for k in ('axp717', 'axp323', 'dcdc3_setpoint_mV'))", """            assert observed['dcdc3_setpoint_mV'] == voltage['dcdc3_setpoint_mV'] == 1260
            for chip, changed, ceiling in (('axp717','0x83',65),('axp323','0x13',50)):
                assert all(observed[chip][key] == value for key,value in voltage[chip].items() if key != changed)
                selector = int(observed[chip][changed],16)
                assert selector & 128 == int(voltage[chip][changed],16) & 128
                assert 40 <= (selector & 127) <= ceiling""")
text=text.replace("'actual_khz': [int((p/'scaling_cur_freq').read_text()) for p in POLICIES],", """'actual_khz': [int((p/'scaling_cur_freq').read_text()) for p in POLICIES],
                 'CPU_DCDC1_setpoint_mV': Path('/sys/module/tzx_cpufreq_dvfs/parameters/rail_mv').read_text().strip(),
                 'lease_seconds': 30,""")
(root/'firmware/tzx_cpu_dvfs_runtime.py').write_text(text)
unit=(root/'firmware/tzx-cpu-performance.service').read_text().replace('tzx-cpu-performance','tzx-cpu-dvfs').replace('cpu-performance-','cpu-dvfs-')
unit=unit.replace('qualified fixed-voltage CPU performance','qualified CPU DCDC1 DVFS')
unit=unit.replace('tzx-gpu-performance.service\n','tzx-gpu-performance.service tzx-cpu-performance.service\n')
(root/'firmware/tzx-cpu-dvfs.service').write_text(unit)
print('QUALIFIED_DVFS_RUNTIME_PREPARED')
