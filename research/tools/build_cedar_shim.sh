#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
out="$base/vpu-cedar-port"
mkdir -p "$out"
test ! -f "$out/STARTED"
touch "$out/STARTED"
mkdir -p "$out/drivers/media/platform/sunxi"
cp "$base/linux-7.3.3/drivers/media/platform/sunxi/Kconfig" \
    "$base/linux-7.3.3/drivers/media/platform/sunxi/Makefile" "$out/drivers/media/platform/sunxi/"
for number in 0085 0104 0110 0128 0129 0131; do
    for reference in "$task_root"/upstream/performance-reference/$number-*.patch; do
        patch --batch --fuzz=0 -d "$out" -p1 < "$reference"
    done
done
