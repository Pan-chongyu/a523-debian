"""Bounded opt-in HS profiles; only preallocated scratch-file direct I/O."""
import array,fcntl,hashlib,json,mmap,os,re,subprocess,sys,threading,time
from pathlib import Path
root=Path('/home/debian/hs-kernel');scratch=root/'hs-scratch.bin'
size=128*1024*1024
param=Path('/sys/module/tzx_emmc_hs_lease/parameters')
if len(sys.argv)==2 and sys.argv[1]=='io-worker':
    expected=hashlib.shake_256(b'TZX HS mode scratch check v1').digest(size)
    sha=hashlib.sha256(expected).hexdigest()
    buf=mmap.mmap(-1,size);fd=os.open(scratch,os.O_RDWR|os.O_DIRECT)
    result=[]
    try:
        for i in range(2):
            buf[:]=expected;started=time.monotonic()
            assert os.pwritev(fd,[buf],0)==size;os.fsync(fd)
            written=time.monotonic()-started;buf[:]=bytes(size);started=time.monotonic()
            assert os.preadv(fd,[buf],0)==size;read=time.monotonic()-started
            assert hashlib.sha256(buf).hexdigest()==sha
            result.append(dict(bytes=size,sha256=sha,write_MiB_s=round(128/written,2),read_MiB_s=round(128/read,2)))
        print(json.dumps(result),flush=True)
    finally:os.close(fd);buf.close()
    raise SystemExit(0)
assert os.geteuid()==0 and len(sys.argv)==3
mode,mhz=map(int,sys.argv[1:]);assert mode in (200,400) and 25<=mhz<=200
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert hashlib.sha256((root/'tzx_emmc_hs_lease.ko').read_bytes()).hexdigest()=='4fff4ab723d4360232feac530cc3f7726658b58e9c04dd5ac5e034f647152ed1'
assert not param.exists()
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if not scratch.exists():
    fd=os.open(scratch,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
    os.posix_fallocate(fd,0,size);os.fsync(fd);os.close(fd)
assert scratch.stat().st_size==size
stop=threading.Event();limit=time.monotonic()+160
wd=None;thread=None
def ping():
    while not stop.wait(2):
        if time.monotonic()<limit:os.write(wd,b'.')
loaded=False;renew_stop=threading.Event();renew=None
try:
    subprocess.run(['insmod',str(root/'tzx_emmc_hs_lease.ko'),'lease_seconds=10'],check=True,timeout=15)
    loaded=True
    print('HS_PROFILE_REQUEST',mode,mhz,flush=True)
    guard=Path('/run/emmc-transition-guard')
    assert guard.is_file() and mhz==100
    subprocess.run([str(guard),f'{mode},{mhz}'],check=True,timeout=135)
    wd=os.open('/dev/watchdog',os.O_WRONLY|os.O_CLOEXEC)
    seconds=array.array('i',[16]);fcntl.ioctl(wd,0xc0045706,seconds,True)
    thread=threading.Thread(target=ping,daemon=True);thread.start()
    ios=Path('/sys/kernel/debug/mmc0/ios').read_text()
    print('HS_PROFILE_SELECTED',ios,flush=True)
    expected_timing='mmc HS200' if mode==200 else 'mmc HS400'
    assert expected_timing in ios and int((param/'fault').read_text())==0
    baseline=Path('/sys/kernel/debug/mmc0/err_stats').read_text()
    def renew_loop():
        while not renew_stop.wait(1):
            if time.monotonic()<limit:(param/'renew').write_text('1')
    renew=threading.Thread(target=renew_loop,daemon=True);renew.start()
    child=subprocess.run([sys.executable,__file__,'io-worker'],capture_output=True,text=True,timeout=75)
    print('HS_DIRECT_IO',child.stdout,child.stderr,flush=True);assert child.returncode==0
    assert Path('/sys/kernel/debug/mmc0/err_stats').read_text()==baseline
    assert int((param/'fault').read_text())==0
    data=dict(status='PASS',boot_id=boot,mode=mode,requested_mhz=mhz,actual_hz=int((param/'actual_hz').read_text()),
        ios=ios,transfers=json.loads(child.stdout),errors_after_tuning=baseline,
        iommu_errors=next(s for s in Path('/proc/interrupts').read_text().splitlines() if s.rstrip().endswith('2010000.iommu')))
    renew_stop.set();renew.join(3)
    # Explicit normal-protocol fallback is verified before testing lease expiry.
    (param/'profile').write_text('0,25')
    assert 'mmc DDR52' in Path('/sys/kernel/debug/mmc0/ios').read_text()
    assert Path('/sys/kernel/debug/mmc0/clock').read_text().strip()=='25000000'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
    data['protocol_fallback_verified']=True
    (root/f'qualified-{mode}-{mhz}.json').write_text(json.dumps(data,indent=2)+'\n')
    print('HS_PROFILE_DIRECT_IO_AND_PROTOCOL_RESTORE_PASS',json.dumps(data),flush=True)
finally:
    renew_stop.set()
    if renew:renew.join(3)
    if loaded:
        subprocess.run(['rmmod','tzx_emmc_hs_lease'],check=True,timeout=30)
    stop.set()
    if thread:thread.join(3)
    if wd is not None:os.write(wd,b'V');os.close(wd)
