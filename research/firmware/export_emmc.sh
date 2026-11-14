#!/bin/busybox sh
set -eu
trap '' HUP
[ "$(cat /sys/class/block/mmcblk0/device/cid)" = 3e01ff55454d20202010209170281b59 ]
[ "$(cat /sys/class/block/mmcblk0/size)" = 244318208 ]
if grep -q '/dev/mmcblk' /proc/mounts; then exit 20; fi
g=/sys/kernel/config/usb_gadget/tzx
mkdir -p "$g/functions/mass_storage.0"
echo 1 > "$g/functions/mass_storage.0/stall"
echo 0 > "$g/functions/mass_storage.0/lun.0/ro"
echo 0 > "$g/functions/mass_storage.0/lun.0/removable"
echo /dev/mmcblk0 > "$g/functions/mass_storage.0/lun.0/file"
udc=$(cat "$g/UDC")
echo '' > "$g/UDC"
ln -s "$g/functions/mass_storage.0" "$g/configs/c.1/mass_storage.0"
echo "$udc" > "$g/UDC"
