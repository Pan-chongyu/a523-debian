#!/bin/sh
# One-shot panel identification using the reference CLDO1/4 + PD22 wiring.
# Voltages are checked, never changed. No panel vendor init or HS video.
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '3e01ff55454d20202010209170281b59'
test "$(uname -r)" = '7.3.3-tzx-a523'
test ! -L /sys/bus/i2c/devices/0-0034/driver
test ! -d /sys/module/tzx_dsi_probe
test "$(sha256sum /home/debian/tzx_dsi_probe.ko | cut -d ' ' -f1)" = '9523a868860aa13896954dd3edf7424db49e8c43eea417a1f7f574fc688c6b49'
test "$(i2cget -y 0 0x34 0x9b)" = '0x0d' # CLDO1 1.8V
test "$(i2cget -y 0 0x34 0x9e)" = '0x1c' # CLDO4 3.3V
original=$(i2cget -y 0 0x34 0x91)
test "$original" = '0xd7'
python3 /home/debian/read_display_state.py > /home/debian/dsi-panel-before.json
cleanup() {
    rmmod tzx_dsi_probe 2>/dev/null || true
    i2cset -y 0 0x34 0x91 "$original"
    python3 /home/debian/read_display_state.py > /home/debian/dsi-panel-after.json
    cat /home/debian/dsi-panel-after.json
    dmesg | grep 'TZX DSI:' | tail -n 16
}
trap cleanup EXIT HUP INT TERM
i2cset -y 0 0x34 0x91 0xdf
test "$(i2cget -y 0 0x34 0x91)" = '0xdf'
sleep 1
insmod /home/debian/tzx_dsi_probe.ko probe_panel=1 vc="${1:-0}"
cat /sys/module/tzx_dsi_probe/parameters/report
