"""Configure the board's initial XFCE session after package installation."""
from pathlib import Path
import os
import pwd
import subprocess

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
def write(name, text, user=False):
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if user:
        account = pwd.getpwnam('debian')
        os.chown(path, account.pw_uid, account.pw_gid)
        for parent in path.parents:
            if parent == Path('/home/debian'):
                break
            os.chown(parent, account.pw_uid, account.pw_gid)

write('/etc/NetworkManager/conf.d/10-tzx-usb-unmanaged.conf', '''[keyfile]
unmanaged-devices=interface-name:usb0
''')
write('/etc/X11/xorg.conf.d/20-tzx-display.conf', '''Section "Device"
    Identifier "TZX A523 DE350"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card0"
    Option "AccelMethod" "none"
    Option "ShadowFB" "true"
    Option "PageFlip" "false"
    Option "SWcursor" "true"
EndSection
''')
write('/etc/lightdm/lightdm.conf.d/50-tzx-tablet.conf', '''[Seat:*]
autologin-user=debian
autologin-user-timeout=0
user-session=xfce
greeter-session=lightdm-gtk-greeter
''')
write('/etc/systemd/system/lightdm.service.d/10-tzx-display.conf', '''[Unit]
Requires=tzx-display.service
After=tzx-display.service
''')
write('/home/debian/.dmrc', '''[Desktop]
Session=xfce
''', user=True)
write('/home/debian/.config/autostart/tzx-onboard.desktop', '''[Desktop Entry]
Type=Application
Name=Screen keyboard
Exec=onboard
OnlyShowIn=XFCE;
X-GNOME-Autostart-enabled=true
''', user=True)
write('/home/debian/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0">
  <property name="Xft" type="empty">
    <property name="DPI" type="int" value="144"/>
  </property>
  <property name="Gtk" type="empty">
    <property name="FontName" type="string" value="Sans 11"/>
    <property name="TouchscreenMode" type="bool" value="true"/>
  </property>
</channel>
''', user=True)
subprocess.run(['usermod', '-aG', 'video,render,audio,netdev,bluetooth', 'debian'], check=True)
# Both locales are useful over SSH, while the tablet itself starts in Chinese.
write('/etc/locale.gen', 'en_US.UTF-8 UTF-8\nzh_CN.UTF-8 UTF-8\n')
subprocess.run(['locale-gen'], check=True)
subprocess.run(['update-locale', 'LANG=zh_CN.UTF-8'], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', 'lightdm.service', 'NetworkManager.service'], check=True)
subprocess.run(['systemctl', 'set-default', 'graphical.target'], check=True)
print('XFCE_TABLET_SESSION_CONFIGURED')
