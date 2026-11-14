#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/tzx-codec-module"
mkdir -p "$out" "$task_root/build/audio-codec"
cp "$task_root/firmware/tzx_codec.c" "$out/"
dtc -@ -I dts -O dtb "$task_root/firmware/tzx_codec_overlay.dts" -o "$out/codec.dtbo"
cat > "$out/overlay.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_codec_overlay
tzx_codec_overlay:
.incbin "codec.dtbo"
.global tzx_codec_overlay_end
tzx_codec_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
# Build the matching, unmodified mainline helper sources as modules. They
# have no built-in code dependency; SND_SOC/SND_PCM are already modules.
cp "$source/sound/core/pcm_dmaengine.c" "$source/sound/soc/soc-generic-dmaengine-pcm.c" "$out/"
cat > "$out/Makefile" <<'EOF'
obj-m := tzx_codec_driver.o tzx_pcm_dmaengine.o tzx_generic_dmaengine_pcm.o
tzx_codec_driver-y := tzx_codec.o overlay.o
tzx_pcm_dmaengine-y := pcm_dmaengine.o
tzx_generic_dmaengine_pcm-y := soc-generic-dmaengine-pcm.o
asflags-y := -I$(src)
EOF
make -C "$source" O="$base/kernel-peripheral-build" M="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/"*.ko "$task_root/build/audio-codec/"
sha256sum "$out/"*.ko
