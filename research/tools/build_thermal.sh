#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/tzx-thermal-acceleration"
artifacts="$task_root/build/thermal-acceleration"
mkdir -p "$out/drivers/thermal" "$artifacts"
cp "$source/drivers/thermal/sun8i_thermal.c" "$out/drivers/thermal/"
for name in 0021-thermal-sun8i-add-sun55i-a523-ths.patch 0022-thermal-sun8i-add-sun55i-a523-ddr-ths.patch; do
    patch --batch --forward -d "$out" -p1 < "$task_root/upstream/trimui-reference/kernel/patches/$name"
done
python3 "$task_root/tools/prepare_thermal_port.py" "$out/drivers/thermal/sun8i_thermal.c"
cp "$out/drivers/thermal/sun8i_thermal.c" "$out/"
cp "$source/drivers/thermal/thermal_hwmon.h" "$out/"
cp "$task_root/firmware/tzx_thermal_overlay.c" "$out/"
dtc -@ -I dts -O dtb "$task_root/firmware/tzx_thermal_overlay.dts" -o "$out/thermal.dtbo"
fdtput -r "$out/thermal.dtbo" /__symbols__
fdtoverlay -i "$task_root/build/periph1-desktop-verified/boot/board.dtb" \
    -o "$artifacts/merged-verification.dtb" "$out/thermal.dtbo"
cat > "$out/thermal_blob.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_thermal_overlay
tzx_thermal_overlay:
.incbin "thermal.dtbo"
.global tzx_thermal_overlay_end
tzx_thermal_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
cat > "$out/Makefile" <<'EOF'
obj-m := tzx_thermal_driver.o tzx_thermal_nodes.o
tzx_thermal_driver-y := sun8i_thermal.o
tzx_thermal_nodes-y := tzx_thermal_overlay.o thermal_blob.o
asflags-y := -I$(src)
EOF
make -C "$source" O="$base/kernel-acceleration-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/"*.ko "$out/thermal.dtbo" "$out/sun8i_thermal.c" "$artifacts/"
sha256sum "$artifacts/"*.ko "$artifacts/thermal.dtbo"
