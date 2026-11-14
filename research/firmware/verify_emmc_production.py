"""Actual eMMC service recovery and GPU/RAM/direct-file coexistence."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

assert len(sys.argv) == 2 and sys.argv[1] in ('online','reboot')
MODE = sys.argv[1]
ROOT = Path('/home/debian/emmc-performance')
FILE = ROOT/'performance-scratch.bin'
STATE = Path('/var/lib/tzx')
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
UNIT = 'tzx-emmc-performance.service'
PARAM = Path('/sys/module/tzx_emmc_performance/parameters')
peaks, actual_cpu = {}, [0,0]
children, streams, events = [], [], []
started = time.monotonic()
xorg = subprocess.check_output(['pgrep','-x','Xorg'],text=True).strip()
assert not FILE.exists()

def run(*args,timeout=100):
    p = subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    assert p.returncode == 0,(args,p.returncode,p.stdout[-2000:],p.stderr[-1000:])
    return p.stdout

def active():
    for unused in range(100):
        p = Path('/run/tzx-emmc-performance.json')
        if p.exists() and PARAM.exists():
            s = json.loads(p.read_text())
            if s['boot_id'] == BOOT and s['state'] == 'active' and Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '50000000':
                return
        time.sleep(0.25)
    raise RuntimeError('eMMC performance did not become ready')

def sample():
    assert time.monotonic()-started < 240
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
    assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
    assert run('pgrep','-x','Xorg').strip() == xorg
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '50000000'
    assert Path('/sys/kernel/debug/mmc0/err_state').read_text().strip() == '0'
    assert int((PARAM/'fault').read_text()) == 0
    assert int(Path('/sys/kernel/debug/clk/gpu/clk_rate').read_text()) == 600000000
    for index,cpu in enumerate((0,4)):
        p = Path('/sys/devices/system/cpu/cpufreq/policy'+str(cpu))
        assert (p/'scaling_max_freq').read_text().strip() == str((792000,1008000)[index])
        actual_cpu[index] = max(actual_cpu[index],int((p/'scaling_cur_freq').read_text()))
    for p in Path('/sys/class/thermal').glob('thermal_zone*'):
        name,temp = (p/'type').read_text().strip(),int((p/'temp').read_text())
        assert 0<temp<70000,(name,temp)
        peaks[name] = max(peaks.get(name,0),temp)
    assert not [s for s in run('dmesg').splitlines() if re.search(
        r'panfrost.*(fault|timeout)|\bBUG:|\bOops:|\bSError\b|mmc0.*(error|timeout|CRC)|I/O error|EXT4-fs error',s,re.I)]
    for name in ('screen_buffer_errors','screen_panel_errors'):
        assert int((Path('/sys/module/tzx_display/parameters')/name).read_text()) == 0

try:
    active()
    for kind,key in (('screen','result'),('dram-gpu','status')):
        h = json.loads((STATE/(kind+'-boot-health.json')).read_text())
        assert h['boot_id'] == BOOT and h[key] == 'PASS'
    if MODE == 'online':
        run('systemctl','stop',UNIT)
        assert not PARAM.exists()
        assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
        run('systemctl','start',UNIT)
        active()
        events.append('normal service stop restores 25MHz; restart 50MHz PASS')
        run('systemctl','kill','--kill-whom=main','--signal=SIGKILL',UNIT)
        for unused in range(100):
            if not PARAM.exists():
                break
            time.sleep(0.25)
        assert not PARAM.exists()
        assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
        run('systemctl','reset-failed',UNIT)
        run('systemctl','start',UNIT)
        active()
        events.append('SIGKILL supervisor: independent cleanup restores 25MHz; restart PASS')
    else:
        installed = json.loads((STATE/'emmc-performance-installed.json').read_text())
        assert installed['installed_boot_id'] != BOOT
        shutdown = run('journalctl','-b','-1','-u',UNIT,'--no-pager')
        assert 'EMMC_PERFORMANCE_ORIGINAL_25MHZ_RESTORED' in shutdown
        (ROOT/'previous-boot-emmc-service.log').write_text(shutdown)
        events.append('real normal reboot: original 25MHz shutdown and automatic 50MHz startup PASS')
    sample()
    fd = os.open(FILE,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
    try:
        os.posix_fallocate(fd,0,128*1024*1024)
        os.fsync(fd)
    finally:
        os.close(fd)
    commands = {
        'direct-io':['python3','-u','/home/debian/verify_emmc_performance.py','io-worker'],
        'memory':['/home/debian/memory-check-bounded','2560'],
        'gpu':['runuser','-u','debian','--','env','DISPLAY=:0','XAUTHORITY=/home/debian/.Xauthority',
               'glmark2-es2','--size','640x480','--off-screen','-b',':duration=1']}
    for name,command in commands.items():
        stream = (ROOT/(MODE+'-'+name+'.log')).open('w')
        streams.append(stream)
        children.append(subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT))
    while any(p.poll() is None for p in children):
        sample()
        time.sleep(0.5)
    assert all(p.returncode == 0 for p in children),[(p.pid,p.returncode) for p in children]
    for stream in streams:
        stream.close()
    texts = {n:(ROOT/(MODE+'-'+n+'.log')).read_text() for n in commands}
    assert 'DIRECT_SCRATCH_IO_PASS' in texts['direct-io']
    assert 'MEMORY_TEST_2560_MIB_8_THREADS_PASS' in texts['memory']
    assert 'Mali-G57 (Panfrost)' in texts['gpu'] and 'Error:' not in texts['gpu']
    score = int(re.search(r'glmark2 Score:\s*(\d+)',texts['gpu'])[1])
    assert actual_cpu == [792000,1008000],actual_cpu
    audit = run('python3','/home/debian/verify_safe_memory.py','--files-only')
    assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit
    sample()
    assert not run('systemctl','--failed','--no-legend','--plain').strip()
    run('systemctl','is-active',UNIT,'tzx-cpu-performance.service','tzx-gpu-performance.service',
        'tzx-wifi.service','tzx-bluetooth.service')
    manifest = json.loads(Path('/usr/local/lib/tzx-emmc-performance/manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest,name
    record = {'status':'PASS','mode':MODE,'boot_id':BOOT,'events':events,
        'eMMC_actual_clock_hz':50000000,'actual_cpu_maximum_khz':actual_cpu,'gpu_hz':600000000,
        'GPU_score_with_IO_and_2560MiB_memory':score,'peaks_mc':peaks,'xorg_pid_unchanged':xorg,
        'direct_io':texts['direct-io'],'memory':texts['memory'],'file_audit':audit,
        'mmc_errors':run('cat','/sys/kernel/debug/mmc0/err_stats'),
        'screen_errors':0,'normal_reboot_verified':MODE=='reboot',
        'poweroff_key_on_verified':False,'elapsed':round(time.monotonic()-started,2)}
    target = STATE/('emmc-performance-validation-'+MODE+'.json')
    assert not target.exists()
    target.write_text(json.dumps(record,indent=2)+'\n')
    for suffix in ('installed','qualified'):
        p = STATE/('emmc-performance-'+suffix+'.json')
        current = json.loads(p.read_text())
        current[MODE+'_production_validation'] = {'status':'PASS','boot_id':BOOT,'record':str(target),
            'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        if MODE == 'reboot':
            current['normal_reboot_verified'] = True
        temp = p.with_suffix('.json.verified')
        temp.write_text(json.dumps(current,indent=2)+'\n')
        temp.replace(p)
    print('EMMC_PRODUCTION_'+MODE.upper()+'_PASS',json.dumps(record),flush=True)
except BaseException:
    subprocess.run(['systemctl','stop',UNIT],timeout=45)
    raise
finally:
    for p in children:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=10)
    for stream in streams:
        stream.close()
    FILE.unlink(missing_ok=True)
