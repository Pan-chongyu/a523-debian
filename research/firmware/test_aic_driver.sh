#!/bin/sh
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '3e01ff55454d20202010209170281b59'
test "$(uname -r)" = '7.3.3-tzx-a523'
test "$(cat /sys/bus/sdio/devices/mmc1:390b:1/vendor)" = '0xc8a1'
test "$(cat /sys/bus/sdio/devices/mmc1:390b:1/device)" = '0x0082'
test "$(cat /sys/kernel/debug/mmc1/clock)" = '12000000'
test ! -d /sys/module/aic8800_bsp
test ! -d /sys/module/aic8800_fdrv
test "$(sha256sum /home/debian/radxa-aic-candidate.tar.gz | cut -d ' ' -f1)" = '851b86bdb43aadd82a7c3e774a2c2a2ebf03f4519cfac7953fa9541b8fff00ec'
stage=/home/debian/radxa-aic-stage
mkdir -p "$stage"
tar -xzf /home/debian/radxa-aic-candidate.tar.gz --no-same-owner -C "$stage"
(cd "$stage" && sha256sum -c SHA256SUMS)
mkdir -p /lib/firmware
for file in "$stage"/lib/firmware/*; do
    test -f "$file"
    install -m644 "$file" /lib/firmware/
done
insmod "$stage/lib/modules/7.3.3-tzx-a523/extra/aic8800_bsp.ko"
sleep 2
insmod "$stage/lib/modules/7.3.3-tzx-a523/extra/aic8800_fdrv.ko"
sleep 3
echo AIC_DRIVER_MODULES_LOADED
ip -brief link
iw dev
dmesg | tail -n 85
