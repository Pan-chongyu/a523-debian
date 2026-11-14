#!/bin/sh
# Explicitly powered, reversible touch test on the verified base device tree.
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '$(cat /etc/tzx/device-cid)'
test "$(uname -r)" = '7.3.3-tzx-a523-accel1'
test ! -d /sys/firmware/devicetree/base/touch-i2c
test ! -L /sys/bus/i2c/devices/0-0034/driver
state=/run/tzx-touch-runtime-cldo2
case "${1:-}" in
start)
    test ! -e "$state"
    test ! -d /sys/module/tzx_gsl3670
    test ! -d /sys/module/tzx_touch_runtime
    test ! -d /sys/bus/i2c/devices/i2c-1
    test "$(i2cget -y 0 0x34 0x9c)" = '0x1c'
    original=$(i2cget -y 0 0x34 0x91)
    case "$original" in 0xd5|0xd7) ;; *) exit 11;; esac
    test "$(sha256sum /usr/local/lib/tzx-peripherals-accel1/silead-seeedd1001-candidate.fw | cut -d ' ' -f1)" = '125728ad83424e533198f804cb6d8b393c59d3818903760cbda282138e782636'
    test "$(sha256sum /usr/local/lib/tzx-peripherals-accel1/tzx_gsl3670.ko | cut -d ' ' -f1)" = 'dd25a872e7459896063d50c9b0baa486a8c36c997eec749715c8014827bd1778'
    test "$(sha256sum /usr/local/lib/tzx-peripherals-accel1/tzx_touch_runtime.ko | cut -d ' ' -f1)" = 'fca5b74118002d48671455b1847ba784e4a744b2d0864a20744ef5264ac735dd'
    printf '%s\n' "$original" > "$state"
    cleanup() {
        rmmod tzx_touch_runtime 2>/dev/null || true
        rmmod tzx_gsl3670 2>/dev/null || true
        i2cset -y 0 0x34 0x91 "$original"
        rm -f "$state" /run/tzx-touch-rail-ready.json /run/tzx-touch-input-ready.json
    }
    trap cleanup EXIT HUP INT TERM
    install -D -m644 /usr/local/lib/tzx-peripherals-accel1/silead-seeedd1001-candidate.fw /lib/firmware/silead/tzx-p30-candidate.fw
    i2cset -y 0 0x34 0x91 0xd7
    test "$(i2cget -y 0 0x34 0x91)" = '0xd7'
    if test -n "${NOTIFY_SOCKET:-}"; then
        /usr/bin/python3 /usr/local/lib/tzx-screen-fast/touch_ready.py rails
    fi
    sleep 1
    insmod /usr/local/lib/tzx-peripherals-accel1/tzx_gsl3670.ko
    insmod /usr/local/lib/tzx-peripherals-accel1/tzx_touch_runtime.ko
    test -L /sys/bus/i2c/devices/1-0040/driver
    test "$(basename "$(readlink -f /sys/bus/i2c/devices/1-0040/driver)")" = 'tzx-gsl3670'
    trap - EXIT HUP INT TERM
    if test -n "${NOTIFY_SOCKET:-}"; then
        /usr/bin/python3 /usr/local/lib/tzx-screen-fast/touch_ready.py input
    fi
    echo RUNTIME_TOUCH_DRIVER_BOUND_CLDO2_3V3
    cat /proc/bus/input/devices
    grep -i 'PH9\|gsl\|1-0040' /proc/interrupts || true
    dmesg | tail -n 25
    ;;
stop)
    test -f "$state"
    original=$(cat "$state")
    case "$original" in 0xd5|0xd7) ;; *) exit 12;; esac
    rmmod tzx_touch_runtime
    rmmod tzx_gsl3670
    i2cset -y 0 0x34 0x91 "$original"
    test "$(i2cget -y 0 0x34 0x91)" = "$original"
    rm -f "$state" /run/tzx-touch-rail-ready.json /run/tzx-touch-input-ready.json
    test ! -d /sys/bus/i2c/devices/i2c-1
    echo RUNTIME_TOUCH_DEVICES_REMOVED_CLDO2_RESTORED
    ;;
*) echo 'usage: tzx-touch-runtime-test.sh start|stop' >&2; exit 2;;
esac
