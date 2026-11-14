#!/bin/sh
# Build the qualified sources against the exact target kernel configuration.
set -eu
if [ "$#" -ne 3 ]; then
    echo "Usage: sh $0 KERNEL_SOURCE KERNEL_BUILD OUTPUT_DIRECTORY" >&2
    exit 2
fi
research_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
kernel_source=$(CDPATH= cd -- "$1" && pwd)
kernel_build=$(CDPATH= cd -- "$2" && pwd)
mkdir -p "$3"
output=$(CDPATH= cd -- "$3" && pwd)
mkdir -p "$output/display" "$output/power"
cp "$research_root/firmware/screen-boot-console/"* "$output/display/"
printf '#define TZX_PANEL_COMPONENT\n#include "tzx_dsi_probe.c"\n' > "$output/display/tzx_panel_link.c"
printf 'obj-m := tzx_display.o\ntzx_display-y := tzx_drm.o tzx_panel_link.o\n' > "$output/display/Makefile"
cp "$research_root/firmware/sun55i-pck600-live-preserve.c" "$output/power/sun55i-pck600.c"
printf 'obj-m := sun55i-pck600.o\n' > "$output/power/Makefile"
cross=${CROSS_COMPILE:-aarch64-linux-gnu-}
make -C "$kernel_source" O="$kernel_build" M="$output/display" ARCH=arm64 CROSS_COMPILE="$cross" -j4 modules
make -C "$kernel_source" O="$kernel_build" M="$output/power" ARCH=arm64 CROSS_COMPILE="$cross" -j4 modules
"${cross}gcc" -O2 -Wall -Wextra -Werror -Wl,--build-id=none -s \
    -o "$output/render-log" "$research_root/firmware/boot_console_render.c"
# The font retains the kernel's GPL licensing. Extract only the actual 4096
# initializer bytes; comments also contain hex examples and must be excluded.
python3 - "$kernel_source/lib/fonts/font_8x16.c" "$output/font8x16.bin" <<'PY'
from pathlib import Path
import re
import sys
source = Path(sys.argv[1]).read_text()
source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
source = source[source.index('static const struct font_data'):]
source = source[source.index('{', source.index('FONTDATAMAX')) + 1:] if 'FONTDATAMAX' in source else source
values = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-fA-F]{2})\b', source))
assert len(values) == 4096, len(values)
Path(sys.argv[2]).write_bytes(values)
PY
sha256sum "$output/display/tzx_display.ko" "$output/power/sun55i-pck600.ko" \
    "$output/render-log" "$output/font8x16.bin"
