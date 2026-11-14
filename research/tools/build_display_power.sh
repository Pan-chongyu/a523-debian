#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/tzx-display-power"
artifacts="$task_root/build/gpu-acceleration"
mkdir -p "$out" "$artifacts"
phandle=$(fdtget -t x "$task_root/build/periph1-desktop-verified/boot/board.dtb" /soc/power-controller@7060000 phandle)
case "$phandle" in ''|*[!0-9a-f]*) exit 2 ;; esac
cp "$task_root/firmware/tzx_display_power.c" "$out/"
cat > "$out/power.dts" <<EOF
/dts-v1/;
/plugin/;
/ {
    fragment@0 {
        target-path = "/";
        __overlay__ {
            tzx-display-vo0 {
                compatible = "tzx,p30-display-power";
                power-domains = <0x$phandle 3>;
            };
            tzx-display-vo1 {
                compatible = "tzx,p30-display-power";
                power-domains = <0x$phandle 4>;
            };
            tzx-display-de {
                compatible = "tzx,p30-display-power";
                power-domains = <0x$phandle 5>;
            };
        };
    };
};
EOF
dtc -@ -I dts -O dtb "$out/power.dts" -o "$out/power.dtbo"
fdtoverlay -i "$task_root/build/periph1-desktop-verified/boot/board.dtb" -o "$artifacts/power-merged-verification.dtb" "$out/power.dtbo"
cat > "$out/power_blob.S" <<'EOF'
.section .rodata
.balign 8
.global tzx_power_overlay
tzx_power_overlay:
.incbin "power.dtbo"
.global tzx_power_overlay_end
tzx_power_overlay_end:
.section .note.GNU-stack,"",%progbits
EOF
cat > "$out/Makefile" <<EOF
obj-m := tzx_display_domains.o
tzx_display_domains-y := tzx_display_power.o power_blob.o
ccflags-y := -DTZX_PCK_PHANDLE=0x$phandle
asflags-y := -I\$(src)
EOF
make -C "$base/linux-7.3.3" O="$base/kernel-acceleration-build" M="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$out/tzx_display_domains.ko" "$out/power.dtbo" "$out/power.dts" "$artifacts/"
sha256sum "$artifacts/tzx_display_domains.ko"
