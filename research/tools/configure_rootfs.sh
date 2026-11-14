#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
rootfs=/opt/a523-debian-20261109/rootfs
printf '%s\n' tzx-a523 > "$rootfs/etc/hostname"
cat > "$rootfs/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 tzx-a523
::1 localhost ip6-localhost ip6-loopback
EOF
cat > "$rootfs/etc/apt/sources.list" <<'EOF'
deb https://deb.debian.org/debian trixie main contrib non-free-firmware
deb https://deb.debian.org/debian trixie-updates main contrib non-free-firmware
deb https://security.debian.org/debian-security trixie-security main contrib non-free-firmware
EOF
cat > "$rootfs/etc/fstab" <<'EOF'
LABEL=DEBIAN_ROOT / ext4 defaults,noatime 0 1
LABEL=DEBIAN_BOOT /boot vfat defaults,nofail,x-systemd.device-timeout=60 0 2
EOF
printf '%s\n' 'TZX P30A523_20T5G 3e01ff55454d20202010209170281b59' > "$rootfs/etc/tzx-board-id"
printf '%s\n' 'LANG=C.UTF-8' > "$rootfs/etc/default/locale"
ln -sfn /proc/self/mounts "$rootfs/etc/mtab"
ln -sfn /usr/share/zoneinfo/Asia/Shanghai "$rootfs/etc/localtime"
printf '%s\n' Asia/Shanghai > "$rootfs/etc/timezone"
truncate -s0 "$rootfs/etc/machine-id"
mkdir -p "$rootfs/etc/systemd/system/getty.target.wants"
ln -sfn /usr/lib/systemd/system/serial-getty@.service \
    "$rootfs/etc/systemd/system/getty.target.wants/serial-getty@ttyGS0.service"
mkdir -p "$rootfs/usr/local/sbin" "$rootfs/etc/systemd/system/multi-user.target.wants"
cp "$task_root/firmware/tzx-usb-network" "$rootfs/usr/local/sbin/tzx-usb-network"
cp "$task_root/build/enable-cpub" "$rootfs/usr/local/sbin/tzx-enable-cpub"
chmod 755 "$rootfs/usr/local/sbin/tzx-usb-network" "$rootfs/usr/local/sbin/tzx-enable-cpub"
cp "$task_root/firmware/tzx-usb-network.service" "$task_root/firmware/tzx-cpub.service" "$rootfs/etc/systemd/system/"
ln -sfn ../tzx-usb-network.service "$rootfs/etc/systemd/system/multi-user.target.wants/tzx-usb-network.service"
ln -sfn ../tzx-cpub.service "$rootfs/etc/systemd/system/multi-user.target.wants/tzx-cpub.service"
if ! chroot "$rootfs" id debian >/dev/null 2>&1; then
    chroot "$rootfs" /usr/sbin/useradd -m -s /bin/bash -G sudo debian
fi
python3 - "$task_root" "$rootfs" <<'PY'
from pathlib import Path
import secrets, subprocess, sys
project, rootfs = map(Path, sys.argv[1:])
credentials = project / 'private/initial-login.txt'
if not credentials.exists():
    password = secrets.token_urlsafe(15)
    subprocess.run(['chroot',str(rootfs),'/usr/sbin/chpasswd'],input=f'debian:{password}\n',text=True,check=True)
    credentials.write_text('Username: debian\nPassword: '+password+'\nChange this password after the first login.\n')
PY
mkdir -p "$rootfs/boot"
cp "$task_root/build/Image" "$rootfs/boot/Image-7.3.3-tzx-a523"
cp "$task_root/build/board.dtb" "$rootfs/boot/board.dtb"
cp "$task_root/build/kernel.config" "$rootfs/boot/config-7.3.3-tzx-a523"
cp "$task_root/build/initramfs.cpio.gz" "$rootfs/boot/initramfs-tzx.cpio.gz"
rm -f "$rootfs/usr/bin/qemu-aarch64-static"
chroot "$rootfs" /usr/bin/apt-get clean
chroot "$rootfs" /usr/bin/dpkg --audit
chroot "$rootfs" /bin/sh -c 'cat /etc/debian_version; dpkg --print-architecture; test -x /sbin/init; test -x /usr/sbin/resize2fs; id debian'
