#!/bin/sh
# Test the reference SDIO startup sequence without changing rail voltages.
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '$(cat /etc/tzx/device-cid)'
test "$(uname -r)" = '7.3.3-tzx-a523-accel1'
test ! -L /sys/bus/i2c/devices/0-0034/driver
state=/run/tzx-wifi-runtime-ldo-enable
case "${1:-}" in
start)
    test ! -e "$state"
    test ! -d /sys/module/tzx_wifi_runtime
    test ! -d /sys/bus/platform/devices/4021000.mmc
    # ALDO3=3.3V, BLDO1/BLDO2=1.8V; preserve those voltage registers.
    test "$(i2cget -y 0 0x34 0x95)" = '0x1c'
    test "$(i2cget -y 0 0x34 0x97)" = '0x0d'
    test "$(i2cget -y 0 0x34 0x98)" = '0x0d'
    original=$(i2cget -y 0 0x34 0x90)
    case "$original" in 0x2c|0x3c) ;; *) exit 11;; esac
    test "$(sha256sum /usr/local/lib/tzx-peripherals-accel1/tzx_wifi_runtime.ko | cut -d ' ' -f1)" = 'c89472e3d800beba1796940a7c6afc78d82d22166f7a72b4ae9310caf222c751'
    printf '%s\n' "$original" > "$state"
    cleanup() {
        rmmod tzx_wifi_runtime 2>/dev/null || true
        i2cset -y 0 0x34 0x90 "$original"
        rm -f "$state"
    }
    trap cleanup EXIT HUP INT TERM
    i2cset -y 0 0x34 0x90 0x3c
    test "$(i2cget -y 0 0x34 0x90)" = '0x3c'
    sleep 1
    insmod /usr/local/lib/tzx-peripherals-accel1/tzx_wifi_runtime.ko bus_width=4 max_frequency_mhz=24
    sleep 2
    test -L /sys/bus/platform/devices/tzx-mmc1-runtime/driver
    trap - EXIT HUP INT TERM
    echo RUNTIME_SDIO_HOST_BOUND
    ls /sys/bus/sdio/devices
    dmesg | tail -n 35
    ;;
stop)
    test -f "$state"
    original=$(cat "$state")
    case "$original" in 0x2c|0x3c) ;; *) exit 12;; esac
    rmmod tzx_wifi_runtime
    i2cset -y 0 0x34 0x90 "$original"
    test "$(i2cget -y 0 0x34 0x90)" = "$original"
    rm -f "$state"
    echo RUNTIME_SDIO_REMOVED_RAIL_ENABLE_RESTORED
    ;;
*) echo 'usage: tzx-wifi-runtime-test.sh start|stop' >&2; exit 2;;
esac
