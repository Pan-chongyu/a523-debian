"""Record the tested boot bundle and the fresh reinstall images separately."""
import hashlib,json
from datetime import datetime,timezone
from fel_device import ROOT,EXPECTED_CID,CAPACITY
b=ROOT/'build'
evidence=(ROOT/'evidence/FINAL-VERIFICATION.txt').read_text(encoding='utf-8')
assert 'TZX_DEBIAN_FINAL_REBOOT_VALIDATION_PASS' in evidence
assert '7.3.3-tzx-a523 #3' in evidence
manifest=json.loads((b/'linux-bundle.json').read_text())
assert manifest['sha256']=='1460fc74e00b811f5fdf734b5c75181486dfd4104a543edcc669e496100e2a8a'
manifest.update(hardware_boot_verified=True,verification_evidence='evidence/FINAL-VERIFICATION.txt',
                verified_kernel_build=3)
(b/'linux-bundle.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
names=['Image','board.dtb','initramfs.cpio.gz','linux-bundle.bin','chain-loader.toc0',
       'debian-rootfs.ext4','debian-rootfs.ext4.gz','debian-boot.fat','debian-boot.fat.gz',
       'gpt-primary.bin','gpt-backup.bin','kernel.config','enable-cpub']
items=[]
for name in names:
    path=b/name;h=hashlib.sha256()
    with path.open('rb') as f:
        while data:=f.read(1048576):h.update(data)
    items.append({'file':name,'bytes':path.stat().st_size,'sha256':h.hexdigest()})
by_name={x['file']:x for x in items}
assert by_name['linux-bundle.bin']['sha256']==manifest['sha256']
assert by_name['Image']['sha256']==manifest['items'][0]['sha256']
assert by_name['debian-rootfs.ext4']['sha256']==(b/'debian-rootfs.ext4.sha256').read_text().split()[0]
report={'recorded_utc':datetime.now(timezone.utc).isoformat(),'board':'TZX P30A523_20T5G',
        'emmc_cid':EXPECTED_CID,'user_sectors':CAPACITY,
        'installed_system':'Debian 13.7 arm64; Linux 7.3.3-tzx-a523 build 3',
        'tested_installed_boot_bundle':manifest['sha256'],
        'reinstall_images_note':'Rebuilt from the fresh source rootfs with final fixes; not a byte-for-byte image of the running, expanded filesystem.',
        'complete_tablet_peripheral_port':False,
        'not_yet_adapted':['display','touch','Wi-Fi','Bluetooth','GPU','audio','camera','battery/charging','suspend'],
        'artifacts':items,'verification_evidence':'evidence/FINAL-VERIFICATION.txt'}
(b/'ARTIFACTS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(b/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['file']+'\n' for x in items),encoding='ascii',newline='\n')
print('Final artifact manifest written. Boot bundle verified on the tablet; reinstall images identified separately.')
