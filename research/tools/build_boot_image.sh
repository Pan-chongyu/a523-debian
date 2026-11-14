#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
boot_image=/opt/a523-debian-20261109/debian-boot.fat
truncate -s 512M "$boot_image"
mkfs.vfat -F32 -n DEBIAN_BOOT "$boot_image"
mcopy -o -i "$boot_image" "$task_root/build/Image" ::Image
mcopy -o -i "$boot_image" "$task_root/build/board.dtb" ::board.dtb
mcopy -o -i "$boot_image" "$task_root/build/initramfs.cpio.gz" ::initramfs.cpio.gz
fsck.vfat -n "$boot_image"
cp --sparse=always "$boot_image" "$task_root/build/debian-boot.fat"
sha256sum "$task_root/build/debian-boot.fat"
