"""Follow the changed DTB header with the existing exact eMMC runtime guard."""
import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');record=json.loads((state/'boot-logo-installed.json').read_text())
assert record['toc0_sha256']=='fc208e752fc816e1e016944cd0f4c4d9497989ec174718e5f3b12d030136b0ca'
sha=lambda b:hashlib.sha256(b).hexdigest()
target=Path('/usr/local/lib/tzx-emmc-hs/manifest.json');old=target.read_bytes();value=json.loads(old)
assert value['boot_header_sha256']=='1e07c2743da3e94c0e6f498b4c7a5203c9f7666e3c66b819f64633eb8742ddbb'
for name,digest in value['files'].items():assert sha(Path(name).read_bytes())==digest,name
assert value['kernel_image_sha256']=='470dd0c350c7ef7aad392eac3a35237672862f0fffdacea8da4e6adb6740e6e4'
fd=os.open('/dev/mmcblk0',os.O_RDONLY)
try:header=os.pread(fd,512,4096*512)
finally:os.close(fd)
assert sha(header)==record['raw_invariants']['header']
value['boot_header_sha256']=sha(header)
data=(json.dumps(value,indent=2)+'\n').encode()
backup=Path(record['backup'])/'files'/str(target).lstrip('/');assert not backup.exists()
def atomic(path,data,mode=0o600):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.logo-new')
    with temporary.open('wb') as f:f.write(data);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
    temporary.replace(path)
mode=target.stat().st_mode&0o777;atomic(backup,old,mode);atomic(target,data,mode)
record['files'][str(target)]=dict(original_sha256=sha(old),installed_sha256=sha(data),mode=mode)
record['eMMC_qualified_manifest_follows_actual_reserved_DTB_header']=True
atomic(state/'boot-logo-installed.json',(json.dumps(record,indent=2)+'\n').encode())
failure=json.loads((state/'emmc-hs-failure.json').read_text())
assert failure['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert failure['error']=="AssertionError('screen-boot-health.json')"
proof=(state/'emmc-hs-revoked.json').read_bytes();qualified=json.loads(proof)
assert qualified['trial']['status']=='PASS' and qualified['trial']['protocol_fallback_verified']
assert qualified['controls']['lease_expiry_verified'] and qualified['controls']['post_expiry_direct_io_verified']
assert not (state/'emmc-hs-qualified.json').exists()
atomic(state/'emmc-hs-qualified.json',proof)
os.sync()
subprocess.run(['systemctl','start','tzx-emmc-hs'],check=True,timeout=160)
status=json.loads(Path('/run/tzx-emmc-hs.json').read_text())
assert status['state']=='active' and status['actual_hz']==100000000
print('BOOT_LOGO_EXACT_HEADER_GUARD_AND_QUALIFIED_HS200_RESTORED',json.dumps(status),flush=True)
