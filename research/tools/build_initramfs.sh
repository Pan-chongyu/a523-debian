#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
initrd_root=/opt/a523-debian-20261109/initramfs
mkdir -p "$initrd_root/bin" "$initrd_root/dev" "$initrd_root/proc" "$initrd_root/sys" "$initrd_root/run" "$initrd_root/tmp"
dpkg-deb -x "$task_root/downloads/busybox-static-arm64.deb" "$initrd_root"
cp "$initrd_root/usr/bin/busybox" "$initrd_root/bin/busybox"
qemu-aarch64-static "$initrd_root/bin/busybox" sh -n "$task_root/firmware/initramfs-init"
qemu-aarch64-static "$initrd_root/bin/busybox" true
cp "$task_root/firmware/initramfs-init" "$initrd_root/init"
chmod 755 "$initrd_root/init"
cd "$initrd_root"
find . -print0 | cpio --null -o --format=newc | gzip -1 > "$task_root/build/initramfs.cpio.gz"
sha256sum "$task_root/build/initramfs.cpio.gz"
