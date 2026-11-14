"""Run bounded desktop GLES workloads with temperature and kernel checks."""
import json, os, subprocess, time
from pathlib import Path
assert os.uname().release == '7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
command=['runuser','-u','debian','--','env','DISPLAY=:0','XAUTHORITY=/home/debian/.Xauthority','stdbuf','-oL','-eL','glmark2-es2','--size','400x400','--off-screen']
command += ['-b',':duration=2']
faults=lambda:[line for line in subprocess.check_output(['dmesg'],text=True).splitlines() if 'panfrost' in line and any(word in line for word in ['fault','timeout'])]
before=faults()
zones=list(Path('/sys/class/thermal').glob('thermal_zone*'))
assert len(zones)==5
started=time.monotonic()
log=Path('/home/debian/gpu-workload-extended.log')
with log.open('w') as output:
    process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
    try:
        while process.poll() is None:
            values={p.joinpath('type').read_text().strip():int(p.joinpath('temp').read_text()) for p in zones}
            print(json.dumps({'second':round(time.monotonic()-started,2),'temperatures_mC':values}),flush=True)
            assert all(0<t<75000 for t in values.values()),'Temperature guard'
            assert time.monotonic()-started<180,'Workload deadline'
            assert faults()==before,'New Panfrost fault during workload'
            time.sleep(2)
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
text=log.read_text()
print(text,flush=True)
assert process.returncode==0,process.returncode
assert 'Mali-G57 (Panfrost)' in text,text
assert 'glmark2 Score:' in text,text
assert not int(Path('/proc/sys/kernel/tainted').read_text()) & 128
assert faults()==before
print('GPU_EXTENDED_WORKLOAD_PASS',flush=True)
