#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
module="$base/tzx-gpu-devfreq"
artifacts="$task_root/build/gpu-devfreq"
mkdir -p "$module" "$artifacts"
cp "$task_root/firmware/tzx_gpu_devfreq_nodes.c" "$task_root/firmware/tzx_gpu_devfreq_guard.c" "$module/"
dtc -@ -I dts -O dtb "$task_root/firmware/tzx_gpu_devfreq_overlay.dts" -o "$module/gpu-devfreq.dtbo"
fdtput -r "$module/gpu-devfreq.dtbo" /__symbols__
cat > "$module/blob.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_gpu_devfreq_overlay
tzx_gpu_devfreq_overlay:
.incbin "gpu-devfreq.dtbo"
.global tzx_gpu_devfreq_overlay_end
tzx_gpu_devfreq_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
cat > "$module/Makefile" <<'EOF'
obj-m := tzx_gpu_devfreq_opps.o tzx_gpu_devfreq_guard.o
tzx_gpu_devfreq_opps-y := tzx_gpu_devfreq_nodes.o blob.o
asflags-y := -I$(src)
EOF
make -C "$base/linux-hs-source" O="$base/kernel-hs-build" M="$module" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$module/"*.ko "$artifacts/"
cp "$module/gpu-devfreq.dtbo" "$artifacts/"
sha256sum "$artifacts/"*.ko
