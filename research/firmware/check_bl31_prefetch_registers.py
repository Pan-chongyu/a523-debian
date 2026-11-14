"""Read all eight A55 controls; the module has no register-write path."""
import hashlib
import os
from pathlib import Path
import re
import subprocess

assert os.geteuid() == 0 and os.uname().release == '7.3.3-tzx-a523-accel1'
assert '#5 ' in os.uname().version
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-7'
assert not Path('/sys/module/tzx_cpu_stream_probe').exists()
probe = Path('/home/debian/tzx_cpu_stream_readonly.ko')
assert hashlib.sha256(probe.read_bytes()).hexdigest() == 'daed55465d9d3bcbfda55f167565fc097d95cc0e5326b8c08b9072428d235533'
subprocess.run(['insmod', str(probe)], check=True, timeout=20)
try:
    rows = subprocess.check_output(['dmesg'], text=True).splitlines()
    rows = [row for row in rows if 'tzx-cpu-stream: cpu' in row][-8:]
    assert len(rows) == 8
    states = {}
    for row in rows:
        print(row, flush=True)
        match = re.search(r'cpu([0-7]) midr=412fd050 cpuectlr=([0-9a-f]+)', row)
        assert match, row
        states[int(match[1])] = int(match[2], 16)
    assert states == {cpu: 0x28081000 for cpu in range(8)}, states
finally:
    subprocess.run(['rmmod', 'tzx_cpu_stream_probe'], check=True, timeout=20)
print('PREFETCH_CONTROL_EIGHT_CORES_READBACK_PASS', flush=True)
