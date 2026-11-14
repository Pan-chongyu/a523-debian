#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-lradc-keys"
mkdir -p "$out" "$task_root/build/lradc-keys"
cp "$task_root/firmware/tzx_lradc_keys.c" "$out/"
dtc -@ -I dts -O dtb "$task_root/firmware/tzx_lradc_keys.dts" -o "$out/lradc.dtbo"
fdtoverlay -i "$task_root/build/periph1-desktop-verified/boot/board.dtb" \
    -o "$task_root/build/lradc-keys/merged-verification.dtb" "$out/lradc.dtbo"
cat > "$out/lradc_blob.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_lradc_overlay
tzx_lradc_overlay:
.incbin "lradc.dtbo"
.global tzx_lradc_overlay_end
tzx_lradc_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
cat > "$out/Makefile" <<'EOF'
obj-m := tzx_lradc_keyboard.o
tzx_lradc_keyboard-y := tzx_lradc_keys.o lradc_blob.o
asflags-y := -I$(src)
EOF
make -C "$base/linux-7.3.3" O="$base/kernel-acceleration-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_lradc_keyboard.ko" "$out/lradc.dtbo" "$task_root/build/lradc-keys/"
sha256sum "$task_root/build/lradc-keys/tzx_lradc_keyboard.ko"
