#!/bin/sh
set -eu
rootfs=/opt/a523-debian-20261109/rootfs
chroot "$rootfs" /bin/sh -c 'dpkg -i /var/cache/apt/archives/*.deb'
