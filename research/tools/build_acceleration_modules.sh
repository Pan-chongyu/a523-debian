#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
source="$base/linux-7.3.3"
out="$base/kernel-acceleration-build"
artifacts="$task_root/build/acceleration-kernel"
module_out="$base/tzx-acceleration-modules"
mkdir -p "$module_out" "$artifacts/peripherals"
cp "$task_root/firmware/"tzx_drm.c "$task_root/firmware/"tzx_de_scanout.c \
    "$task_root/firmware/"tzx_dsi_probe.c "$task_root/firmware/"tzx_dsi_phy.h \
    "$task_root/firmware/"tzx_dsi_video.h "$module_out/"
cp "$task_root/firmware/"tzx_gsl3670.c "$task_root/firmware/"tzx_touch_runtime.c \
    "$task_root/firmware/"tzx_wifi_runtime.c "$task_root/firmware/"tzx_bt_runtime.c \
    "$task_root/firmware/"tzx_battery.c "$task_root/firmware/"tzx_codec.c "$module_out/"
printf '#define TZX_PANEL_COMPONENT\n#include "tzx_dsi_probe.c"\n' > "$module_out/tzx_panel_link.c"
dtc -@ -I dts -O dtb "$task_root/firmware/tzx_codec_overlay.dts" -o "$module_out/codec.dtbo"
cat > "$module_out/overlay.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_codec_overlay
tzx_codec_overlay:
.incbin "codec.dtbo"
.global tzx_codec_overlay_end
tzx_codec_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
cp "$source/sound/core/pcm_dmaengine.c" "$source/sound/soc/soc-generic-dmaengine-pcm.c" "$module_out/"
cat > "$module_out/Makefile" <<'EOF'
obj-m := tzx_display.o tzx_gsl3670.o tzx_touch_runtime.o tzx_wifi_runtime.o tzx_bt_runtime.o tzx_battery.o
obj-m += tzx_codec_driver.o tzx_pcm_dmaengine.o tzx_generic_dmaengine_pcm.o
tzx_display-y := tzx_drm.o tzx_panel_link.o
tzx_codec_driver-y := tzx_codec.o overlay.o
tzx_pcm_dmaengine-y := pcm_dmaengine.o
tzx_generic_dmaengine_pcm-y := soc-generic-dmaengine-pcm.o
asflags-y := -I$(src)
EOF
printf 'ccflags-y := -I%s/drivers/mmc/core\n' "$source" >> "$module_out/Makefile"
make -C "$source" O="$out" M="$module_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j8 modules
cp "$module_out/"*.ko "$artifacts/peripherals/"
aic_out="$base/radxa-aic8800-acceleration"
if [ ! -d "$aic_out" ]; then
    cp -a "$base/radxa-aic8800-port" "$aic_out"
    make -C "$source" O="$out" M="$aic_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- clean
fi
make -C "$source" O="$out" M="$aic_out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    CONFIG_PLATFORM_ALLWINNER=n CONFIG_PLATFORM_ROCKCHIP=n CONFIG_AIC8800_BTLPM_SUPPORT=n \
    CONFIG_USE_FW_REQUEST=y CONFIG_AIC8800_WLAN_SUPPORT=m CONFIG_AIC_WLAN_SUPPORT=m -j8 modules
cp "$aic_out/aic8800_bsp/aic8800_bsp.ko" "$aic_out/aic8800_fdrv/aic8800_fdrv.ko" "$artifacts/peripherals/"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 33030144
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
aarch64-linux-gnu-objdump -d "$artifacts/linux-entry.elf" > "$artifacts/linux-entry.disassembly"
sha256sum "$artifacts/peripherals/"*.ko "$artifacts/linux-entry.bin"
