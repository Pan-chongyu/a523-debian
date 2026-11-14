#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-gpu-acceleration"
artifacts="$task_root/build/gpu-acceleration"
mkdir -p "$out" "$artifacts"
cp "$task_root/firmware/tzx_gpu_overlay.c" "$out/"
dtc -@ -I dts -O dtb "$task_root/firmware/tzx_gpu_overlay.dts" -o "$out/gpu.dtbo"
fdtoverlay -i "$task_root/build/periph1-desktop-verified/boot/board.dtb" \
    -o "$artifacts/merged-verification.dtb" "$out/gpu.dtbo"
cat > "$out/gpu_blob.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_gpu_overlay
tzx_gpu_overlay:
.incbin "gpu.dtbo"
.global tzx_gpu_overlay_end
tzx_gpu_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
cat > "$out/Makefile" <<'EOF'
obj-m := tzx_gpu_nodes.o
tzx_gpu_nodes-y := tzx_gpu_overlay.o gpu_blob.o
asflags-y := -I$(src)
EOF
make -C "$base/linux-7.3.3" O="$base/kernel-acceleration-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_gpu_nodes.ko" "$out/gpu.dtbo" "$artifacts/"
sha256sum "$artifacts/tzx_gpu_nodes.ko" "$artifacts/gpu.dtbo"
