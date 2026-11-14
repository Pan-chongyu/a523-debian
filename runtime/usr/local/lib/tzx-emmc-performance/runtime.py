"""Leased exact-board DDR52 performance, fail closed to the original 25MHz."""
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import threading

ROOT = Path('/usr/local/lib/tzx-emmc-performance')
PARAM = Path('/sys/module/tzx_emmc_performance/parameters')
STATE = Path('/var/lib/tzx')
QUALIFIED = STATE/'emmc-performance-qualified.json'
PENDING = STATE/'emmc-performance-pending.json'
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
stop = threading.Event()

def atomic(path,record):
    temporary = path.with_suffix('.json.new')
    temporary.write_text(json.dumps(record,indent=2)+'\n')
    temporary.replace(path)

signal.signal(signal.SIGTERM, lambda *unused: stop.set())
signal.signal(signal.SIGINT, lambda *unused: stop.set())
try:
    manifest = json.loads((ROOT/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest,name
    proof = json.loads(QUALIFIED.read_text())
    assert proof['trial']['status'] == 'PASS' and proof['trial']['lease_expiry_restores_25MHz']
    if PENDING.exists():
        assert json.loads(PENDING.read_text())['boot_id'] == BOOT, 'Unclean previous eMMC performance boot'
    subprocess.run(['python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'],check=True,timeout=30)
    for name,key in (('screen-boot-health.json','result'),('dram-gpu-boot-health.json','status')):
        health = json.loads((STATE/name).read_text())
        assert health['boot_id'] == BOOT and health[key] == 'PASS'
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip() == '25000000'
    atomic(PENDING,{'boot_id':BOOT,'state':'running','clock_hz':50000000})
    subprocess.run(['insmod',str(ROOT/'tzx_emmc_performance.ko')],check=True,timeout=20)
    while not stop.is_set():
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        assert int((PARAM/'fault').read_text()) == 0
        assert Path('/sys/kernel/debug/mmc0/err_state').read_text().strip() == '0'
        errors = [s for s in subprocess.check_output(['dmesg'],text=True).splitlines() if re.search(
            r'\bBUG:|\bOops:|\bSError\b|mmc0.*(error|timeout|CRC)|I/O error|EXT4-fs error',s,re.I)]
        assert not errors,errors
        temperatures = [int((p/'temp').read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*')]
        assert len(temperatures) == 6 and all(0<t<85000 for t in temperatures)
        (PARAM/'requested_mhz').write_text('50')
        assert int((PARAM/'actual_hz').read_text()) == 50000000
        ios = Path('/sys/kernel/debug/mmc0/ios').read_text()
        assert 'actual clock:\t50000000 Hz' in ios
        assert 'timing spec:\t8 (mmc DDR52)' in ios and 'signal voltage:\t1 (1.80 V)' in ios
        atomic(Path('/run/tzx-emmc-performance.json'),{
            'boot_id':BOOT,'state':'active','actual_hz':50000000,'timing':'DDR52',
            'signal_voltage_mV':1800,'bus_width':8,'lease_seconds':30,
            'mode_voltage_buswidth_changed':False,'boot_areas_changed':False})
        stop.wait(5)
except BaseException as error:
    atomic(STATE/'emmc-performance-failure.json',{'boot_id':BOOT,'error':repr(error)})
    if QUALIFIED.exists():
        QUALIFIED.replace(STATE/'emmc-performance-revoked.json')
    raise
finally:
    subprocess.run(['python3',str(ROOT/'cleanup.py')],check=True,timeout=25)
    atomic(Path('/run/tzx-emmc-performance.json'),{'boot_id':BOOT,'state':'stopped','actual_hz':25000000})
