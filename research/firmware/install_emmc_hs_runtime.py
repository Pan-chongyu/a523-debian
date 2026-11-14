"""Install HS200 only after data I/O, protocol fallback, and expiry checks."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
assert os.geteuid()==0
stage=Path('/home/debian/hs-kernel')
out=Path('/usr/local/lib/tzx-emmc-hs')
trial=json.loads((stage/'qualified-200-100.json').read_text())
controls=json.loads((stage/'controls-200-100.json').read_text())
assert trial['status']=='PASS' and trial['protocol_fallback_verified']
assert trial['actual_hz']==100000000 and trial['mode']==200
assert controls['lease_expiry_verified'] and controls['post_expiry_direct_io_verified']
bundle=json.loads((stage/'linux-bundle.json').read_text())
assert hashlib.sha256(Path('/boot/Image').read_bytes()).hexdigest()==bundle['items'][0]['sha256']
out.mkdir(exist_ok=True)
files={}
for src,dest in ((stage/'tzx_emmc_hs_lease.ko',out/'tzx_emmc_hs_lease.ko'),
                 (Path('/home/debian/emmc-transition-guard'),out/'transition-guard'),
                 (Path('/home/debian/tzx_emmc_hs_runtime.py'),out/'runtime.py'),
                 (Path('/home/debian/tzx-emmc-hs.service'),Path('/etc/systemd/system/tzx-emmc-hs.service'))):
    assert src.is_file() and not dest.is_symlink()
    shutil.copyfile(src,dest);dest.chmod(0o755 if dest.name=='transition-guard' else 0o644)
    files[str(dest)]=hashlib.sha256(dest.read_bytes()).hexdigest()
manifest=dict(profile='HS200-100MHz-8bit-1.8V',files=files,
    kernel_image_sha256=bundle['items'][0]['sha256'],boot_header_sha256=bundle['header_sha256'])
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
proof=dict(trial=trial,controls=controls,hs400_qualified=False)
Path('/var/lib/tzx/emmc-hs-qualified.json').write_text(json.dumps(proof,indent=2)+'\n')
Path('/var/lib/tzx/emmc-hs-installed.json').write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run(['systemctl','disable','--now','tzx-emmc-performance.service'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','tzx-emmc-hs.service'],check=True,timeout=170)
print('QUALIFIED_HS200_100MHZ_RUNTIME_INSTALLED',Path('/run/tzx-emmc-hs.json').read_text(),flush=True)
