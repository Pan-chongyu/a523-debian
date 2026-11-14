#!/bin/sh
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '3e01ff55454d20202010209170281b59'
# Install through the host's USB-only tunnel; do not alter tablet routes or
# start a display manager before the matching kernel/display module is ready.
test ! -e /usr/sbin/policy-rc.d
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d
trap 'rm -f /usr/sbin/policy-rc.d' EXIT HUP INT TERM
export DEBIAN_FRONTEND=noninteractive
apt-get -o Acquire::https::Proxy=http://192.168.77.1:3142 -o Acquire::Retries=2 update
apt-get -o Acquire::https::Proxy=http://192.168.77.1:3142 -o Acquire::Retries=2 \
    -y --no-install-recommends install \
    xfce4 lightdm lightdm-gtk-greeter xserver-xorg-core xserver-xorg-input-libinput \
    xserver-xorg-video-fbdev x11-xserver-utils dbus-x11 polkitd pkexec \
    network-manager network-manager-gnome onboard fonts-noto-cjk fonts-dejavu \
    mesa-utils libgl1-mesa-dri firefox-esr pulseaudio pavucontrol alsa-utils \
    bluez blueman evtest libdrm-tests locales curl
echo DESKTOP_PACKAGES_INSTALLED
