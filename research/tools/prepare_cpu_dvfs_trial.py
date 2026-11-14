"""Extend the real-hardware PLL suite with voltage and lease assertions."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
text = (root/'firmware/verify_cpu_performance.py').read_text()
text = text.replace('/home/debian/cpu-performance', '/home/debian/cpu-dvfs')
text = text.replace('tzx_cpufreq_safepll', 'tzx_cpufreq_dvfs')
text = text.replace('tzx_cpu_perf_cooling', 'tzx_cpu_dvfs_cooling')
text = text.replace("ROOT = Path('/home/debian/cpu-dvfs')", """ROOT = Path('/home/debian/cpu-dvfs')
assert hashlib.sha256((ROOT/'tzx_cpufreq_dvfs.ko').read_bytes()).hexdigest() == '68fc4bfbbdb82f1817767796185eb778b1b598b630b826bfb0a51f84198b9a97'
assert hashlib.sha256((ROOT/'tzx_cpu_dvfs_cooling.ko').read_bytes()).hexdigest() == '61fff534d611278395a398384f2d2a9ef2171ab7143fbfefc44dbc8f4e000ac2'
subprocess.run(['systemctl', 'stop', 'tzx-cpu-performance.service'], check=True, timeout=45)
# ExecStopPost queues baseline startup. Wait for both the driver AND its
# cooler before changing governors; the cooler's startup asserts schedutil.
subprocess.run(['systemctl', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service'], check=True, timeout=65)
for attempt in range(100):
    driver_path = Path('/sys/devices/system/cpu/cpufreq/policy4/scaling_driver')
    if driver_path.exists() and driver_path.read_text().strip() == 'tzx-a523-divider':
        break
    time.sleep(0.1)
else:
    raise AssertionError('Baseline driver did not restore')
for cluster in (0,4):
    policy = Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(cluster))
    (policy/'scaling_min_freq').write_text('120000')
    (policy/'scaling_max_freq').write_text('480000')
    (policy/'scaling_governor').write_text('performance')
time.sleep(0.2)
lease_enabled = threading.Event()
lease_enabled.set()
lease_thread = None
lease_error = []
def renew_loop():
    while not stop_ping.is_set():
        if lease_enabled.is_set() and Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').exists():
            try:
                Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').write_text('1')
            except BaseException as error:
                lease_error.append(repr(error))
        stop_ping.wait(1)
""")
text = text.replace('temperature < 65000', 'temperature < 75000')
text = text.replace("    assert not faults, faults", "    assert not faults, faults\n    assert not lease_error, lease_error")
text = text.replace("run('insmod', str(ROOT/'tzx_cpufreq_dvfs.ko'))", """run('insmod', str(ROOT/'tzx_cpufreq_dvfs.ko'), 'lease_seconds=5')
    Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').write_text('1')
    lease_thread = threading.Thread(target=renew_loop, daemon=True)
    lease_thread.start()""")
text = text.replace("((1, (480000, 600000, 792000, 1008000)),\n                                 (0, (480000, 600000, 792000)))", "((1, (480000, 1008000, 1200000, 1344000, 1488000)),\n                                 (0, (480000, 792000, 1008000, 1224000, 1416000)))")
text = text.replace("records.append(dict(stage='new-driver', khz=frequency, **benchmark(cluster*4)))", """observed_voltage = voltage()
            expected = (900 if frequency <= 1008000 else 920 if frequency == 1200000 else 960 if frequency == 1344000 else 1000) if cluster else (900 if frequency <= 792000 else 960 if frequency == 1008000 else 1050 if frequency == 1224000 else 1150)
            key, register = ('axp717','0x83') if not cluster else ('axp323','0x13')
            assert 500+(int(observed_voltage[key][register],16)&127)*10 == expected, observed_voltage
            for name, registers_to_check in (('axp717', ('0x3','0x80','0x84','0x85','0x86','0x98')), ('axp323', ('0x3','0x10','0x14','0x15'))):
                assert all(observed_voltage[name][r] == before_voltage[name][r] for r in registers_to_check), observed_voltage
            records.append(dict(stage='new-driver', khz=frequency, millivolts=expected, **benchmark(cluster*4)))""")
text = text.replace('tune(0, 792000)', 'tune(0, 1416000)')
text = text.replace('tune(1, 1008000)', 'tune(1, 1488000)')
text = text.replace('for frequency in (120000, 480000, 600000, 792000):', 'for frequency in (120000, 480000, 1008000, 1416000):')
text = text.replace('tune(1, 1008000 if frequency == 792000 else frequency)', 'tune(1, 1488000 if frequency == 1416000 else frequency)')
text = text.replace('enumerate((792000, 1008000))', 'enumerate((1416000, 1488000))')
text = text.replace("workload(['/home/debian/cpu-execution-coherency']", "workload(['/home/debian/cpu-dvfs/cpu-dvfs-execution']")
text = text.replace("    assert voltage() == before_voltage, 'PMIC settings changed'", """    state('LEASE_EXPIRY')
    for cluster in (0,1):
        tune(cluster, (1416000,1488000)[cluster], 'performance')
        (POLICIES[cluster]/'scaling_min_freq').write_text('120000')
    lease_enabled.clear()
    time.sleep(7)
    assert all(int((p/'scaling_cur_freq').read_text()) <= 480000 for p in POLICIES)
    assert voltage() == before_voltage, 'Lease expiry did not restore 900mV'
    assert Path('/sys/module/tzx_cpufreq_dvfs/parameters/lease_active').read_text().strip() == '0'
    lease_enabled.set()
    Path('/sys/module/tzx_cpufreq_dvfs/parameters/renew').write_text('1')""")
text = text.replace("'pmic_before_after': before_voltage", "'pmic_before_and_after_lease_expiry': before_voltage, 'lease_expiry_480MHz_900mV': 'PASS'")
text = text.replace("    if replaced:\n", """    lease_enabled.clear()
    stop_ping.set()
    if lease_thread:
        lease_thread.join(timeout=3)
    # Keep the watchdog fed while restoring modules and services.
    if watchdog is not None:
        os.write(watchdog, b'.')
    if replaced:
""")
text = text.replace("        run('systemctl', 'start', 'tzx-cpu-cooling.service')", """        run('systemctl', 'start', 'tzx-cpu-cooling.service')
        assert voltage() == before_voltage, 'Unload did not restore all PMIC registers'
        run('systemctl', 'start', 'tzx-cpu-performance.service')""")
text = text.replace("state('CPU_PERFORMANCE_TRIAL_PASS'", "state('CPU_DVFS_TRIAL_PASS'")
(root/'firmware/verify_cpu_dvfs.py').write_text(text)
execution = (root/'firmware/cpu_execution_coherency.c').read_text()
execution = execution.replace('    check(above_4g > 0, "No high physical pages: comparison inconclusive");',
    '    /* Clock/voltage validation executes every allocated page. The separate\n'
    '     * full-memory suite checks DRAM above 4GiB; report coverage honestly. */\n'
    '    printf("CPU_DVFS_EXECUTION_COVERAGE above_4g=%u\\n", above_4g);')
(root/'firmware/cpu_dvfs_execution.c').write_text(execution)
print('CPU_DVFS_REAL_HARDWARE_TRIAL_PREPARED')
