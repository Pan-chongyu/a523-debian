#!/bin/sh
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '3e01ff55454d20202010209170281b59'
test ! -L /sys/bus/i2c/devices/0-0034/driver
state=/run/tzx-display-test-rail-mask
exec 9>/run/tzx-dsi-live.lock
flock -x 9
if test -d /sys/module/tzx_de_scanout; then rmmod tzx_de_scanout; fi
if test -d /sys/module/tzx_dsi_probe; then rmmod tzx_dsi_probe; fi
if test -f "$state"; then
    original=$(cat "$state")
    test "$original" = '0xd7'
    current=$(i2cget -y 0 0x34 0x91)
    case "$current" in 0xd7|0xdf) ;; *) exit 12;; esac
    i2cset -y 0 0x34 0x91 "$original"
    test "$(i2cget -y 0 0x34 0x91)" = "$original"
    rm -f "$state"
fi
echo TZX_DISPLAY_TEST_STOPPED_RAIL_RESTORED
