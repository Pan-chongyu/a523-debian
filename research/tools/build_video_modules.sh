#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-extended-source";out="$base/kernel-extended-build"
module="$base/tzx-video-runtime";artifacts="$task_root/build/video"
mkdir -p "$module" "$artifacts"
cp "$task_root/firmware/tzx_video_overlay.c" "$module/"
dtc -@ -I dts -O dtb "$task_root/firmware/tzx_video_overlay.dts" -o "$module/video.dtbo"
# The base DT intentionally has no exported symbol namespace. Local fixups
# remain; exporting our two nvmem labels is unnecessary.
fdtput -r "$module/video.dtbo" /__symbols__
cat > "$module/overlay.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_video_overlay
tzx_video_overlay:
.incbin "video.dtbo"
.global tzx_video_overlay_end
tzx_video_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
cat > "$module/Makefile" <<'EOF'
obj-m := tzx_video_nodes.o
tzx_video_nodes-y := tzx_video_overlay.o overlay.o
asflags-y := -I$(src)
EOF
make -C "$source" O="$out" M="$module" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$module/tzx_video_nodes.ko" "$artifacts/"
cp "$task_root/build/extended-kernel/sunxi-ve.ko" "$artifacts/"
tar -C "$base/cedar-userspace" -czf "$artifacts/userspace.tar.gz" etc usr
sha256sum "$artifacts/"*.ko "$artifacts/userspace.tar.gz"
