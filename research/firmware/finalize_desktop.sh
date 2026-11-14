#!/bin/sh
set -eu
export LC_ALL=C DEBIAN_FRONTEND=noninteractive
test "$(cat /sys/class/block/mmcblk0/device/cid)" = 3e01ff55454d20202010209170281b59
test "$(dpkg-query -W -f='${db:Status-Status}' xfce4)" = installed
test ! -e /usr/sbin/policy-rc.d
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d
trap 'rm -f /usr/sbin/policy-rc.d' EXIT HUP INT TERM
python3 - <<'PY'
from pathlib import Path
files = [Path('/etc/apt/sources.list'), *Path('/etc/apt/sources.list.d').glob('*.sources'), *Path('/etc/apt/sources.list.d').glob('*.list')]
for path in files:
    if not path.is_file():
        continue
    old = path.read_text()
    new = old.replace('https://security.debian.org/debian-security', 'https://deb.debian.org/debian-security')
    if new != old:
        path.with_name(path.name+'.tzx-before-cdn').write_text(old)
        path.write_text(new)
PY
apt-get -o Acquire::https::Proxy=http://192.168.77.1:3142 -o Acquire::Retries=2 update
apt-get -o Acquire::https::Proxy=http://192.168.77.1:3142 -o Acquire::Retries=2 \
    -y --no-install-recommends install wpasupplicant lxpolkit xfce4-power-manager xfce4-power-manager-plugins
python3 /home/debian/configure_desktop.py
test -f /usr/share/xsessions/xfce.desktop
test -x /usr/sbin/wpa_supplicant
dpkg --audit
sync
echo TZX_DESKTOP_FINALIZED
