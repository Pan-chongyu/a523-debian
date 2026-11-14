#!/bin/sh
# Run in debian's existing graphical session, not as root.
set -eu
test "$(id -un)" = debian
export DISPLAY=:0 XAUTHORITY=/home/debian/.Xauthority
# XFCE uses dbus-launch rather than the user bus on this minimal image.
session_pid=$(pgrep -u 1000 -x xfce4-session | head -n 1)
test -n "$session_pid"
address=$(tr '\000' '\n' < "/proc/$session_pid/environ" | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p')
test -n "$address"
export DBUS_SESSION_BUS_ADDRESS="$address"
gsettings set org.onboard.window docking-enabled true
gsettings set org.onboard.window docking-edge bottom
gsettings set org.onboard.window.portrait dock-height 270
gsettings set org.onboard.window.landscape dock-height 220
gsettings set org.onboard.window force-to-top true
gsettings set org.onboard.auto-show enabled true
gsettings set org.onboard.auto-show tablet-mode-detection-enabled false
gsettings set org.onboard.auto-show keyboard-device-detection-enabled false
gsettings set org.gnome.desktop.interface toolkit-accessibility true
xdg-user-dirs-update
# PM is not enabled yet. Advertise only display blanking, not sleep support.
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled -n -t bool -s false
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/presentation-mode -n -t bool -s true
xfconf-query -c xfwm4 -p /general/use_compositing -n -t bool -s false
xfconf-query -c xfwm4 -p /general/button_layout -n -t string -s 'O|HMC'
echo TZX_SESSION_SETTINGS_APPLIED
