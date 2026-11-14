#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
rootfs=/opt/a523-debian-20261109/rootfs
image=/opt/a523-debian-20261109/debian-rootfs.ext4
if mountpoint -q "$rootfs/proc"; then umount "$rootfs/proc"; fi
if mountpoint -q "$rootfs/sys"; then umount "$rootfs/sys"; fi
if mountpoint -q "$rootfs/dev/pts"; then umount "$rootfs/dev/pts"; fi
if mountpoint -q "$rootfs/dev"; then umount "$rootfs/dev"; fi
truncate -s 2G "$image"
mkfs.ext4 -F -L DEBIAN_ROOT -E lazy_itable_init=0,lazy_journal_init=0 -d "$rootfs" "$image"
e2fsck -fn "$image"
sha256sum "$image" > /opt/a523-debian-20261109/debian-rootfs.ext4.sha256
cp --sparse=always "$image" "$task_root/build/debian-rootfs.ext4"
cp /opt/a523-debian-20261109/debian-rootfs.ext4.sha256 "$task_root/build/debian-rootfs.ext4.sha256"
