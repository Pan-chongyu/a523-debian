"""Derive a boot-time CPU owner from the exact installed qualified wrapper."""
import hashlib
from pathlib import Path

root=Path(__file__).resolve().parents[1]
text=(root/'build/performance-mode-base/cpu-runtime.py').read_text(encoding='utf-8')
assert hashlib.sha256((root/'build/performance-mode-base/cpu-runtime.py').read_bytes()).hexdigest()=='28d24acd8de9c562fd47758cecfa6f758203d08365fb001cf27f4b3ead018b39'
def replace(old,new):
    global text
    assert text.count(old)==1,old
    text=text.replace(old,new)
replace("import signal\n", "import signal\nimport socket\n")
replace("    health = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())\n    assert health['boot_id'] == BOOT and health['status'] == 'PASS'",
    "    # This owner now precedes GPU and LightDM. An independent boot check\n"
    "    # verifies trained memory and the exact hardware identity first.\n"
    "    health = json.loads(Path('/run/tzx-early-performance-check.json').read_text())\n"
    "    assert health['boot_id'] == BOOT and health['status'] == 'PASS'")
replace("    run('systemctl', 'stop', 'tzx-cpu-performance.service')\n    run('systemctl', 'start', 'tzx-cpufreq.service', 'tzx-cpu-cooling.service')\n    run('systemctl', 'stop', 'tzx-cpu-cooling.service')\n    run('systemctl', 'stop', 'tzx-cpufreq.service')",
    "    assert not Path('/sys/module/tzx_cpufreq_divider').exists()\n"
    "    assert not Path('/sys/module/tzx_cpu_cooling').exists()")
replace("        (policy/'scaling_governor').write_text('schedutil')", "        (policy/'scaling_governor').write_text('performance')")
replace("    voltage_checked = time.monotonic()\n    while", "    ready_notified = False\n    voltage_checked = time.monotonic()\n    while")
replace("        atomic(STATUS, state)\n        quit_event.wait(5)",
    "        state['high_frequency_before_graphical_desktop'] = True\n"
    "        atomic(STATUS, state)\n"
    "        if not ready_notified:\n"
    "            address = os.environ.get('NOTIFY_SOCKET')\n"
    "            assert address, 'Early CPU owner requires systemd readiness notification'\n"
    "            if address.startswith('@'): address = '\\0'+address[1:]\n"
    "            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:\n"
    "                client.connect(address); client.sendall(b'READY=1')\n"
    "            ready_notified = True\n"
    "        quit_event.wait(5)")
compile(text,'tzx_cpu_early_performance_runtime.py','exec')
(root/'firmware/tzx_cpu_early_performance_runtime.py').write_text(text,encoding='utf-8',newline='\n')
print('EARLY_CPU_QUALIFIED_WRAPPER_DERIVED',hashlib.sha256(text.encode()).hexdigest())
text=(root/'build/performance-mode-base/gpu-runtime.py').read_text(encoding='utf-8')
replace(".read_text().strip()=='auto'", ".read_text().strip() in ('auto','on')")
replace("(DEVFREQ/'min_freq').write_text('150000000')", "(DEVFREQ/'min_freq').write_text('600000000')")
(root/'firmware/tzx_gpu_max_performance_runtime.py').write_text(text,encoding='utf-8',newline='\n')
text=(root/'firmware/tzx_gpu_devfreq_startup.py').read_text(encoding='utf-8')
text+="\n# Qualified boot-time performance request; kernel QoS thermal ceilings win.\n(PARAM/'maximum_mhz').write_text('600')\n(DEVFREQ/'max_freq').write_text('600000000')\n(DEVFREQ/'min_freq').write_text('600000000')\nPath('/sys/bus/platform/devices/1800000.gpu/power/control').write_text('on')\nprint('BOOT_GPU_MAXIMUM_QUALIFIED_600MHZ_REQUEST_ACTIVE',flush=True)\n"
(root/'firmware/tzx_gpu_max_performance_startup.py').write_text(text,encoding='utf-8',newline='\n')
