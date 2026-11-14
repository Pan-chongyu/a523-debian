#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_work=/opt/a523-debian-20261109
mkdir -p "$task_work/keys" "$task_root/build"
chmod 700 "$task_work/keys"
if [ ! -f "$task_work/keys/root_key.pem" ]; then
    umask 077
    openssl genrsa -out "$task_work/keys/root_key.pem" 2048
fi
arm-none-eabi-gcc -nostdlib -nostartfiles -ffreestanding -march=armv7-a \
    -Wl,-Ttext=0x44000 -Wl,--build-id=none -o "$task_root/build/cold-marker.elf" "$task_root/firmware/cold_marker.S"
arm-none-eabi-objcopy -O binary "$task_root/build/cold-marker.elf" "$task_root/build/cold-marker.bin"
"$task_work/host-tools/tools/mkimage" -T sunxi_toc0 -a 0x44000 \
    -k "$task_work/keys" -d "$task_root/build/cold-marker.bin" "$task_root/build/cold-marker.toc0"
"$task_work/host-tools/tools/mkimage" -k "$task_work/keys" -l "$task_root/build/cold-marker.toc0"
sha256sum "$task_root/build/cold-marker.bin" "$task_root/build/cold-marker.toc0"
