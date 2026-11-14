#!/bin/sh
set -eu
test "$#" = 3
template=$1
source=$2
out=$3
mkdir -p "$out/initramfs-root"
cd "$out/initramfs-root"
gzip -dc "$template" | cpio --quiet -idmu
cp "$source" init
chmod 755 init
qemu-aarch64-static ./bin/busybox sh -n init
rm -f INSTALLER
find . -print0 | LC_ALL=C sort -z | cpio --quiet --null -o --format=newc | gzip -n -1 > "$out/initramfs.cpio.gz"
touch INSTALLER
find . -print0 | LC_ALL=C sort -z | cpio --quiet --null -o --format=newc | gzip -n -1 > "$out/installer-initramfs.cpio.gz"
rm INSTALLER
