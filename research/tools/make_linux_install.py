"""Generate this exact board's Linux-side install plan from fresh artifacts."""
import hashlib,json
from fel_device import ROOT,CAPACITY,EXPECTED_CID
b=ROOT/'build'
def sha(name):
    h=hashlib.sha256()
    with (b/name).open('rb') as f:
        while data:=f.read(1048576):h.update(data)
    return h.hexdigest()
root_sha=sha('debian-rootfs.ext4');boot_sha=sha('debian-boot.fat')
bundle_sha=sha('linux-bundle.bin');toc_sha=sha('chain-loader.toc0')
primary_sha=sha('gpt-primary.bin');backup_sha=sha('gpt-backup.bin')
bundle=json.loads((b/'linux-bundle.json').read_text())
assert (b/'linux-bundle.bin').stat().st_size==bundle['bytes'] and bundle_sha==bundle['sha256']
assert (b/'chain-loader.toc0').stat().st_size==40960
assert root_sha==(b/'debian-rootfs.ext4.sha256').read_text().split()[0]
compressed={name:sha(name) for name in ('debian-rootfs.ext4.gz','debian-boot.fat.gz','gpt-primary.bin','gpt-backup.bin')}
(b/'install-files.sha256').write_text(''.join(f'{digest}  /tmp/{name}\n' for name,digest in compressed.items()),encoding='ascii',newline='\n')
script=f'''#!/bin/busybox sh
set -eu
set -o pipefail
exec >> /tmp/debian-install.log 2>&1
echo TZX_LINUX_INSTALL_STARTED
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '{EXPECTED_CID}'
test "$(cat /sys/class/block/mmcblk0/size)" = '{CAPACITY}'
if grep -q /dev/mmcblk /proc/mounts; then echo TARGET_MOUNTED; exit 10; fi
echo 1 > /sys/kernel/config/usb_gadget/tzx/functions/mass_storage.0/lun.0/forced_eject
test -z "$(cat /sys/kernel/config/usb_gadget/tzx/functions/mass_storage.0/lun.0/file)"
while read -r expected file; do
    test "$(/tmp/fast-sha256 "$file" | cut -d ' ' -f1)" = "$expected"
done < /tmp/install-files.sha256
echo ROOT_WRITE_STARTED
gzip -dc /tmp/debian-rootfs.ext4.gz | dd of=/dev/mmcblk0 bs=1048576 seek=576 conv=fsync
echo ROOT_READBACK_STARTED
test "$(/tmp/fast-sha256 /dev/mmcblk0 603979776 2147483648 | cut -d ' ' -f1)" = '{root_sha}'
echo ROOT_FULL_SHA256_READBACK_PASS
echo BOOT_WRITE_STARTED
gzip -dc /tmp/debian-boot.fat.gz | dd of=/dev/mmcblk0 bs=1048576 seek=64 conv=fsync
test "$(/tmp/fast-sha256 /dev/mmcblk0 67108864 536870912 | cut -d ' ' -f1)" = '{boot_sha}'
echo BOOT_FULL_SHA256_READBACK_PASS
test "$(/tmp/fast-sha256 /dev/mmcblk0 2097152 {bundle['bytes']} | cut -d ' ' -f1)" = '{bundle_sha}'
test "$(/tmp/fast-sha256 /dev/mmcblk0 131072 40960 | cut -d ' ' -f1)" = '{toc_sha}'
echo BOOT_CHAIN_FULL_SHA256_READBACK_PASS
dd if=/tmp/gpt-backup.bin of=/dev/mmcblk0 bs=512 seek={CAPACITY-33} conv=fsync
test "$(dd if=/dev/mmcblk0 bs=512 skip={CAPACITY-33} count=33 | sha256sum | cut -d ' ' -f1)" = '{backup_sha}'
dd if=/tmp/gpt-primary.bin of=/dev/mmcblk0 bs=512 conv=fsync
test "$(dd if=/dev/mmcblk0 bs=512 count=34 | sha256sum | cut -d ' ' -f1)" = '{primary_sha}'
echo GPT_FULL_SHA256_READBACK_PASS
/tmp/reread-emmc
mkdir -p /verify-root
mount -t ext4 -o ro /dev/mmcblk0p2 /verify-root
test "$(cat /verify-root/etc/tzx-board-id)" = 'TZX P30A523_20T5G {EXPECTED_CID}'
cat /verify-root/etc/debian_version
test -x /verify-root/usr/lib/systemd/systemd
umount /verify-root
cat /proc/partitions
sync
echo FRESH_DEBIAN_FULL_READBACK_VERIFIED_UNBOOTED
'''
(b/'install-debian.sh').write_text(script,encoding='ascii',newline='\n')
(b/'linux-install-plan.json').write_text(json.dumps({'cid':EXPECTED_CID,'root_sha256':root_sha,'boot_sha256':boot_sha,'bundle_sha256':bundle_sha,'toc0_sha256':toc_sha,'compressed':compressed},indent=2))
print('Exact board installer generated with complete SHA256 readback checks.')
