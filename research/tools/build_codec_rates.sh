#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-codec-rates"
mkdir -p "$out"
cp "$task_root/build/audio-rates/tzx_codec.c" "$out/"
cp "$base/linux-7.3.3/sound/core/pcm_dmaengine.c" \
    "$base/linux-7.3.3/sound/soc/soc-generic-dmaengine-pcm.c" "$out/"
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
cat > "$out/Makefile" <<'EOF'
obj-m := tzx_codec_driver.o tzx_pcm_dmaengine.o tzx_generic_dmaengine_pcm.o
tzx_codec_driver-y := tzx_codec.o overlay.o
tzx_pcm_dmaengine-y := pcm_dmaengine.o
tzx_generic_dmaengine_pcm-y := soc-generic-dmaengine-pcm.o
asflags-y := -I$(src)
EOF
make -C "$base/linux-7.3.3" O="$base/kernel-cpufreq-framework-build" M="$out" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_codec_driver.ko" "$task_root/build/audio-rates/"
sha256sum "$task_root/build/audio-rates/tzx_codec_driver.ko"
