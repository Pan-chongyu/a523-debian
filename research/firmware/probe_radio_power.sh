#!/bin/sh
# Temporary SDIO IO-rail test. Existing voltage settings are retained.
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = 3e01ff55454d20202010209170281b59
test "$(i2cget -y 0 0x34 0x90)" = 0x2c
test "$(i2cget -y 0 0x34 0x97)" = 0x0d
trap 'i2cset -y 0 0x34 0x90 0x2c' EXIT HUP INT TERM
i2cset -y 0 0x34 0x90 0x3c
sleep 2
echo BLDO1_ENABLED_WITHOUT_GPIO
ls /sys/bus/sdio/devices
/home/debian/peripheral-gpio-probe radio >/home/debian/radio-power-reset.log 2>&1 &
probe_pid=$!
sleep 3
echo BLDO1_AND_PM1_ENABLED
ls /sys/bus/sdio/devices
for path in /sys/bus/sdio/devices/*; do
    test -d "$path" || continue
    cat "$path/uevent"
done
cat /sys/kernel/debug/mmc1/ios
dmesg | tail -n 15
wait "$probe_pid"
cat /home/debian/radio-power-reset.log
