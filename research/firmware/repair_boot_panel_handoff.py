"""Correct only CCF-owned DSI mux handoff, preserve failure, restore exact proofs."""
import hashlib,json,mmap,os,struct,subprocess,time
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='4615e4bd-0756-4dd2-909e-4e5c831c6722'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert Path('/proc/sys/kernel/tainted').read_text().strip()=='4096'
assert not Path('/sys/module/tzx_display').exists() and not Path('/sys/module/panfrost').exists()
sha=lambda b:hashlib.sha256(b).hexdigest()
installed=json.loads((state/'boot-panel-installed.json').read_text())
for name,item in installed['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
backup=Path('/root/tzx-recovery/boot-panel-early-v2/failed-handoff-1')
assert not backup.exists()
backup.mkdir()
names=('boot-panel-installed.json','boot-panel-stage.json','dram-gpu-revoked.json',
    'screen-boot-pending.json','emmc-hs-failure.json','emmc-hs-revoked.json')
for name in names:(backup/name).write_bytes((state/name).read_bytes())
for command,name in ((['dmesg'],'kernel.txt'),(['journalctl','-b','--no-pager'],'journal.txt')):
    (backup/name).write_text(subprocess.check_output(command,text=True))
old=Path('/usr/local/lib/tzx-boot-panel/handoff.py')
(backup/'handoff-v2-before.py').write_bytes(old.read_bytes())
new=Path('/home/debian/boot_panel_handoff_fixed.py').read_bytes()
compile(new,str(old),'exec')
assert b'if address==0x02001b28:mask=1<<31' in new
old.write_bytes(new)
installed['files'][str(old)]['installed_sha256']=sha(new)
installed['handoff_CCF_mux_preserved_revision']=1
(state/'boot-panel-installed.json').write_text(json.dumps(installed,indent=2)+'\n')
# Correct the unowned module's physical mux to the parent CCF has cached.
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
try:
    with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x02001000) as mm:
        val=struct.unpack_from('<I',mm,0xb28)[0]
        assert val&0x0700001f==0
        struct.pack_into('<I',mm,0xb28,(val&~0x0700001f)|0x02000000)
        assert struct.unpack_from('<I',mm,0xb28)[0]&0x0700001f==0x02000000
finally:os.close(fd)
gpu=Path('/home/debian/recovery-gpu-qualified.json').read_bytes()
hs=Path('/home/debian/recovery-emmc-hs-qualified.json').read_bytes()
assert json.loads(gpu)==json.loads((backup/'dram-gpu-revoked.json').read_text())['previous']
assert hs==(backup/'emmc-hs-revoked.json').read_bytes()
assert not (state/'gpu-qualified').exists() and not (state/'emmc-hs-qualified.json').exists()
for name,data in (('gpu-qualified',gpu),('emmc-hs-qualified.json',hs)):
    (state/name).write_bytes(data);(state/name).chmod(0o600)
subprocess.run(['systemctl','reset-failed'],check=True)
os.sync()
print('CCF_DSI_MUX_PRESERVED_AND_EXACT_PREVIOUS_PROOFS_RESTORED',flush=True)
subprocess.run(['systemctl','start','tzx-display'],check=True,timeout=50)
subprocess.run(['systemctl','start','tzx-gpu','lightdm','tzx-dram-gpu-health','tzx-screen-health'],check=True,timeout=65)
subprocess.run(['systemctl','start','tzx-gpu-performance','tzx-emmc-hs'],check=True,timeout=40)
print('NATIVE_DESKTOP_RESTARTED_AFTER_DSI_CLOCK_REPAIR',flush=True)
