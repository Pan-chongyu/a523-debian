#!/bin/sh
# Default: stop after three minutes. --until-stopped keeps the test active.
set -eu
until_stopped=false
if test "${1:-}" = '--until-stopped'; then
    until_stopped=true
    shift
fi
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '3e01ff55454d20202010209170281b59'
test "$(uname -r)" = '7.3.3-tzx-a523'
test ! -L /sys/bus/i2c/devices/0-0034/driver
test ! -d /sys/module/tzx_dsi_probe
test ! -e /run/tzx-display-test-rail-mask
if test "$until_stopped" = true; then
    if systemctl is-active --quiet tzx-display-test-timeout.timer; then
        systemctl stop tzx-display-test-timeout.timer
    fi
    if systemctl is-active --quiet tzx-display-test-timeout.service; then
        echo 'Previous display cleanup is still running' >&2
        exit 13
    fi
fi
sha256sum -c /home/debian/tzx-display-test.sha256
test "$(i2cget -y 0 0x34 0x9b)" = '0x0d'
test "$(i2cget -y 0 0x34 0x9e)" = '0x1c'
original=$(i2cget -y 0 0x34 0x91)
test "$original" = '0xd7'
printf '%s\n' "$original" > /run/tzx-display-test-rail-mask
trap 'sh /home/debian/stop_display_wake_test.sh' EXIT HUP INT TERM
python3 /home/debian/read_display_state.py > /home/debian/display-wake-before.json
i2cset -y 0 0x34 0x91 0xdf
sleep 1
if test "$until_stopped" = false; then
    systemd-run --unit=tzx-display-test-timeout --on-active=180s --timer-property=AccuracySec=1s \
        /bin/sh /home/debian/stop_display_wake_test.sh
fi
insmod /home/debian/tzx_dsi_probe.ko probe_panel=1 hold=1 "$@"
cat /sys/module/tzx_dsi_probe/parameters/report
dmesg | grep 'TZX DSI:' | tail -n 42
trap - EXIT HUP INT TERM
if test "$until_stopped" = true; then
    echo TZX_DISPLAY_TEST_ACTIVE_UNTIL_STOPPED
else
    echo TZX_DISPLAY_TEST_ACTIVE_180_SECONDS
fi
