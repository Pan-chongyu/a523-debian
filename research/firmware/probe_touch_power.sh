#!/bin/sh
# Temporary rail test: use the existing 3.3 V CLDO2 setting; restore enable mask.
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = 3e01ff55454d20202010209170281b59
test "$(i2cget -y 0 0x34 0x91)" = 0xd5
test "$(i2cget -y 0 0x34 0x9c)" = 0x1c
trap 'i2cset -y 0 0x34 0x91 0xd5' EXIT HUP INT TERM
i2cset -y 0 0x34 0x91 0xd7
/home/debian/peripheral-gpio-probe touch >/home/debian/touch-power-reset.log 2>&1 &
probe_pid=$!
sleep 1
for addr in 0x40 0x41 0x42; do
    printf '%s: ' "$addr"
    i2ctransfer -y 1 w1@"$addr" 0xfc r4 || true
done
for reg in 0x80 0xb0 0xb4 0xb8 0xbc 0xfc; do
    printf '%s: ' "$reg"
    i2ctransfer -y 1 w1@0x40 "$reg" r4 || true
done
wait "$probe_pid"
cat /home/debian/touch-power-reset.log
