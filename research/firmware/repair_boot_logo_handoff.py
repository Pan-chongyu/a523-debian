"""Fix device-memory record reads without changing the installed boot image."""
import hashlib,json,mmap,os,struct,subprocess
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');record=json.loads((state/'boot-logo-installed.json').read_text())
assert record['toc0_sha256']=='fc208e752fc816e1e016944cd0f4c4d9497989ec174718e5f3b12d030136b0ca'
sha=lambda b:hashlib.sha256(b).hexdigest()
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x2d000) as view:
        words=[struct.unpack_from('<I',view,0x600+4*i)[0] for i in range(26)]
finally:os.close(fd)
print('BOOT_LOGO_ALIGNED_RECEIPT',json.dumps(words),flush=True)
assert words[:5]==[0xa523b001,1,0x100,1,0]
runtime=Path('/usr/local/lib/tzx-boot-panel/handoff.py');old=runtime.read_bytes()
assert sha(old)=='6c8e6380b785ef453bfe9229990f219993f06d27f0f443f27b8500e9b0bcac35'
fixed=Path('/home/debian/boot-logo-handoff-fixed.py').read_bytes();compile(fixed,'handoff.py','exec')
assert b"get(0x2d600+4*i)" in fixed
backup=Path(record['backup']);assert not (backup/'revision1-handoff.py').exists()
def atomic(path,data):
    path=Path(path);mode=path.stat().st_mode&0o777 if path.exists() else 0o600
    temp=path.with_name(path.name+'.fix-new')
    with temp.open('wb') as f:f.write(data);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
    temp.replace(path)
def enc(v):return (json.dumps(v,indent=2)+'\n').encode()
atomic(backup/'revision1-handoff.py',old)
atomic(backup/'revision1-installed.json',(state/'boot-logo-installed.json').read_bytes())
atomic(backup/'revision1-panel.json',(state/'boot-panel-installed.json').read_bytes())
atomic(backup/'first-boot-receipt.json',enc(words))
for path in (runtime,Path('/home/debian/boot-logo/handoff.py')):atomic(path,fixed)
atomic('/home/debian/boot-logo/guard-files.json',Path('/home/debian/boot-logo-guard-files-fixed.json').read_bytes())
panel=json.loads((state/'boot-panel-installed.json').read_text())
panel['files'][str(runtime)]['installed_sha256']=sha(fixed)
panel_data=enc(panel);atomic(state/'boot-panel-installed.json',panel_data)
record['files'][str(runtime)]['installed_sha256']=sha(fixed)
record['files'][str(state/'boot-panel-installed.json')]['installed_sha256']=sha(panel_data)
record['handoff_revision']=2;atomic(state/'boot-logo-installed.json',enc(record))
revoked=json.loads((state/'dram-gpu-revoked.json').read_text())
assert revoked['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert revoked['previous']['manual_trials_passed'] and revoked['previous']['profile']=='dram-trained-1260-full4g-dma32-aarch64'
assert not Path('/sys/module/panfrost').exists() and not Path('/sys/module/tzx_display').exists()
assert not (state/'gpu-qualified').exists()
atomic(state/'gpu-qualified',enc(revoked['previous']))
os.sync()
subprocess.run(['python3','/home/debian/install_boot_logo.py','verify',record['toc0_sha256']],check=True)
subprocess.run(['systemctl','reset-failed'],check=True)
subprocess.run(['systemctl','start','tzx-boot-panel-handoff'],check=True,timeout=25)
print('BOOT_LOGO_ALIGNED_SRAM_AND_DE_HANDOFF_REPAIRED',flush=True)
subprocess.run(['systemctl','start','tzx-touch','tzx-display'],check=True,timeout=55)
subprocess.run(['systemctl','start','tzx-cpu-dvfs','tzx-gpu','tzx-gpu-performance','tzx-emmc-hs','lightdm',
                'tzx-dram-gpu-health','tzx-screen-health'],check=True,timeout=100)
print('BOOT_LOGO_NATIVE_ACCELERATED_DESKTOP_RESTORED',flush=True)
