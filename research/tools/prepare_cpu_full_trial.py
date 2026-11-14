"""Reuse the checksum/coherency qualification for the vf0300 high OPPs."""
import hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
text=(root/'firmware/verify_cpu_dvfs.py').read_text()
text=text.replace("ROOT = Path('/home/debian/cpu-dvfs')", "ROOT = Path('/home/debian/cpu-full')")
for old,new in [('tzx_cpufreq_dvfs','tzx_cpufreq_dvfs_v2'),('tzx_cpu_dvfs_cooling','tzx_cpu_dvfs_cooling_v2')]:
 text=text.replace(old,new)
for old,name in [('68fc4bfbbdb82f1817767796185eb778b1b598b630b826bfb0a51f84198b9a97','tzx_cpufreq_dvfs_v2.ko'),('61fff534d611278395a398384f2d2a9ef2171ab7143fbfefc44dbc8f4e000ac2','tzx_cpu_dvfs_cooling_v2.ko')]:
 assert old in text
 text=text.replace(old,hashlib.sha256((root/'build/cpu-full'/name).read_bytes()).hexdigest())
needle="subprocess.run(['systemctl', 'stop', 'tzx-cpu-performance.service'], check=True, timeout=45)"
assert text.count(needle)==1
text=text.replace(needle,"subprocess.run(['systemctl', 'stop', 'tzx-cpu-dvfs.service'], check=True, timeout=70)\n"+needle)
text=text.replace('1488000','1800000')
text=text.replace('(480000, 1008000, 1200000, 1344000, 1800000)', '(480000, 1008000, 1200000, 1344000, 1488000, 1584000, 1680000, 1800000)')
old='else 960 if frequency == 1344000 else 1000) if cluster'
new='else 960 if frequency == 1344000 else 1000 if frequency == 1488000 else 1050 if frequency == 1584000 else 1100 if frequency == 1680000 else 1150) if cluster'
assert old in text;text=text.replace(old,new)
needle="    lease_thread.start()"
text=text.replace(needle,needle+'''
    assert Path('/sys/devices/system/cpu/online').read_text().strip()=='0-7'
    capacities=[int(Path('/sys/devices/system/cpu/cpu%d/cpu_capacity'%i).read_text()) for i in range(8)]
    assert capacities==[725]*4+[1024]*4,capacities
    state('NORMALIZED_SCHEDULER_CAPACITY',capacities=capacities)
''')
needle="    for cluster, frequencies in ((1,"
assert needle in text
text=text.replace("        for frequency in frequencies:\n            state('FREQUENCY_STEP'", "        tune(1-cluster, 120000)\n        for frequency in frequencies:\n            state('FREQUENCY_STEP'")
text=text.replace("/home/debian/cpu-dvfs/cpu-dvfs-execution", "/home/debian/cpu-full/cpu-dvfs-execution")
# Temperature control remains active. Cool between sustained all-core and GPU
# stages so verification does not mistake legitimate throttling for a bad PLL.
needle="    state('CLOCK_TRANSITIONS')"
text=text.replace(needle,'''
    state('COOL_BEFORE_TRANSITIONS')
    for cluster in (0,1): tune(cluster,480000,'schedutil')
    cooling_deadline=time.monotonic()+90
    while max(int((p/'temp').read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*'))>60000:
        guard()
        assert time.monotonic()<cooling_deadline,'Cooling deadline'
        time.sleep(1)
'''+needle)
needle="        run('systemctl', 'start', 'tzx-cpu-performance.service')"
assert text.count(needle)==1
text=text.replace(needle,"        run('systemctl', 'start', 'tzx-cpu-dvfs.service',timeout=85)")
text=text.replace('lease_enabled = threading.Event()', 'lease_exit = threading.Event()\nlease_enabled = threading.Event()')
text=text.replace('while not stop_ping.is_set():', 'while not lease_exit.is_set():')
text=text.replace('''    lease_enabled.clear()
    stop_ping.set()
    if lease_thread:''','''    lease_enabled.clear()
    lease_exit.set()
    if lease_thread:''')
text=text.replace("    subprocess.run", "    subprocess.run")
text=text.replace("subprocess.run(['systemctl', 'stop', 'tzx-cpu-dvfs.service']", "subprocess.run(['systemctl', 'stop', 'tzx-emmc-hs.service'], check=True, timeout=55)\nsubprocess.run(['systemctl', 'stop', 'tzx-cpu-dvfs.service']")
text=text.replace("(ROOT/'trial-state.json').write_text(json.dumps(record, indent=2)+'\\n')", """with (ROOT/'trial-state.json').open('w') as stream:
        stream.write(json.dumps(record,indent=2)+'\\n');stream.flush();os.fsync(stream.fileno())""")
text=text.replace("'kernel_taint': 4096,", "'kernel_taint': 4096, 'speed_bin': 'vf0300', 'capacity': capacities,")
# Always release the watchdog even if a restoration assertion fails. Keep its
# ping worker alive throughout the potentially slow systemd rollback.
start=text.index('finally:\n    for child in children:')+len('finally:\n')
end=text.index('    stop_ping.set()\n    if ping_thread:',start)
cleanup=text[start:end]
text=text[:start]+'    try:\n'+''.join('    '+line+'\n' for line in cleanup.splitlines())+'    finally:\n'+''.join('    '+line+'\n' for line in text[end:text.index('if outcome is not None:',end)].splitlines())+text[text.index('if outcome is not None:',end):]
(root/'firmware/verify_cpu_full.py').write_text(text,newline='\n')
print('HIGH_OPP_TRIAL_PREPARED')
