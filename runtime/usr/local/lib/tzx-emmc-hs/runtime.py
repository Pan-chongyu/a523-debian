"""Run only the qualified HS200/100 MHz profile, with kernel lease fallback."""
import hashlib,json,os,signal,socket,subprocess,sys,threading,time
from pathlib import Path

ROOT=Path('/usr/local/lib/tzx-emmc-hs')
PARAM=Path('/sys/module/tzx_emmc_hs_lease/parameters')
STATE=Path('/var/lib/tzx')
PENDING=STATE/'emmc-hs-pending.json'
QUALIFIED=STATE/'emmc-hs-qualified.json'
BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
stop=threading.Event()

def run(*args,timeout=60):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)

def atomic(path,value):
    temporary=path.with_suffix('.json.new')
    with temporary.open('w') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    temporary.replace(path)

def cleanup():
    if PARAM.exists():
        (PARAM/'profile').write_text('0,25')
        run('rmmod','tzx_emmc_hs_lease',timeout=35)
    assert 'mmc DDR52' in Path('/sys/kernel/debug/mmc0/ios').read_text()
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip()=='25000000'
    PENDING.unlink(missing_ok=True)
    atomic(Path('/run/tzx-emmc-hs.json'),dict(boot_id=BOOT,state='baseline',actual_hz=25000000,timing='DDR52'))

assert os.geteuid()==0 and sys.argv[1] in ('run','restore')
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()==Path('/etc/tzx/device-cid').read_text().strip()
if sys.argv[1]=='restore':
    cleanup();raise SystemExit(0)
signal.signal(signal.SIGTERM,lambda *_:stop.set())
signal.signal(signal.SIGINT,lambda *_:stop.set())
try:
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    proof=json.loads(QUALIFIED.read_text())
    assert proof['trial']['status']=='PASS' and proof['trial']['protocol_fallback_verified']
    assert proof['controls']['lease_expiry_verified'] and proof['controls']['post_expiry_direct_io_verified']
    assert proof['trial']['mode']==200 and proof['trial']['actual_hz']==100000000
    if PENDING.exists():
        assert json.loads(PENDING.read_text())['boot_id']==BOOT,'Unclean previous eMMC HS boot'
    for name,key in (('screen-boot-health.json','result'),('dram-gpu-boot-health.json','status')):
        record=json.loads((STATE/name).read_text())
        assert record['boot_id']==BOOT and record[key]=='PASS',name
    assert hashlib.sha256(Path('/boot/Image').read_bytes()).hexdigest()==manifest['kernel_image_sha256']
    with Path('/dev/mmcblk0').open('rb',buffering=0) as disk:
        disk.seek(4096*512)
        assert hashlib.sha256(disk.read(512)).hexdigest()==manifest['boot_header_sha256']
    assert 'sunxi_mmc_tzx_mode' in Path('/proc/kallsyms').read_text()
    assert not PARAM.exists()
    atomic(PENDING,dict(boot_id=BOOT,state='entering-hs200',requested_hz=100000000))
    run('insmod',str(ROOT/'tzx_emmc_hs_lease.ko'))
    run(str(ROOT/'transition-guard'),'200,100',timeout=135)
    baseline=Path('/sys/kernel/debug/mmc0/err_stats').read_text()
    assert all(int(line.rsplit(':',1)[1])==0 for line in baseline.splitlines())
    assert int((PARAM/'actual_hz').read_text())==100000000 and int((PARAM/'fault').read_text())==0
    atomic(Path('/run/tzx-emmc-hs.json'),dict(boot_id=BOOT,state='active',timing='HS200',
        actual_hz=100000000,bus_width=8,signal_voltage_mV=1800,lease_seconds=30,
        errors=baseline,hs400_enabled=False))
    address=os.environ.get('NOTIFY_SOCKET')
    if address:
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock:
            sock.connect('\0'+address[1:] if address.startswith('@') else address)
            sock.sendall(b'READY=1\nSTATUS=HS200 100 MHz, 8-bit, 1.8 V')
    while not stop.is_set():
        assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
        assert int((PARAM/'fault').read_text())==0
        assert Path('/sys/kernel/debug/mmc0/err_stats').read_text()==baseline
        ios=Path('/sys/kernel/debug/mmc0/ios').read_text()
        assert 'mmc HS200' in ios and int((PARAM/'actual_hz').read_text())==100000000
        # CPU cooler replacement can temporarily remove the aggregate zone.
        # Require every physical sensor; do not count optional aggregate zones.
        physical={'cpu-big-thermal','cpu-little-thermal','gpu-thermal','npu-thermal','ddr-thermal'}
        observed={}
        for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
            try:
                name=(zone/'type').read_text().strip()
                if name in physical:observed[name]=int((zone/'temp').read_text())
            except FileNotFoundError:pass
        assert set(observed)==physical
        temperatures=list(observed.values())
        assert all(0<t<80000 for t in temperatures)
        (PARAM/'renew').write_text('1')
        atomic(Path('/run/tzx-emmc-hs.json'),dict(boot_id=BOOT,state='active',timing='HS200',
            actual_hz=100000000,bus_width=8,signal_voltage_mV=1800,lease_seconds=30,
            highest_temperature_mc=max(temperatures),errors=baseline,hs400_enabled=False))
        stop.wait(5)
except BaseException as error:
    atomic(STATE/'emmc-hs-failure.json',dict(boot_id=BOOT,error=repr(error)))
    if QUALIFIED.exists():QUALIFIED.replace(STATE/'emmc-hs-revoked.json')
    raise
finally:
    cleanup()
