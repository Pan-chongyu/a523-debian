#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
rootfs=/opt/a523-debian-20261109/rootfs
chroot "$rootfs" /usr/bin/apt-get update
chroot "$rootfs" /usr/bin/apt-get -y --download-only install util-linux-extra kmod dosfstools i2c-tools
mkdir -p "$task_root/build/target-packages"
cp "$rootfs/var/cache/apt/archives/"*.deb "$task_root/build/target-packages/"
cd "$task_root/build/target-packages"
sha256sum ./*.deb > SHA256SUMS
tar -czf "$task_root/build/target-packages.tar.gz" ./*.deb SHA256SUMS
