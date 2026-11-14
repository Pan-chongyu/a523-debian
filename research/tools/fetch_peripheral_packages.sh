#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
rootfs=/opt/a523-debian-20261109/rootfs
chroot "$rootfs" apt-get -y --download-only install python3-minimal gpiod iw wpasupplicant evtest
mkdir -p "$task_root/build/peripheral-packages"
cp "$rootfs/var/cache/apt/archives/"*.deb "$task_root/build/peripheral-packages/"
cd "$task_root/build/peripheral-packages"
sha256sum ./*.deb > SHA256SUMS
tar -czf "$task_root/build/peripheral-packages.tar.gz" ./*.deb SHA256SUMS
