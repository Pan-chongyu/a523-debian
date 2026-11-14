#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cat "$task_root/build/known-good-base-3/board.dts" \
    "$task_root/firmware/touch-only-additions.dtsi" > "$task_root/build/board-touch-only.dts"
dtc -I dts -O dtb -o "$task_root/build/board-touch-only.dtb" \
    "$task_root/build/board-touch-only.dts"
fdtget "$task_root/build/board-touch-only.dtb" /touch-i2c compatible
fdtget "$task_root/build/board-touch-only.dtb" /touch-i2c/touchscreen@40 compatible
fdtget -t x "$task_root/build/board-touch-only.dtb" /chosen linux,initrd-end
