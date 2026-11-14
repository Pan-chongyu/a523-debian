#!/bin/sh
# Apply the reviewed A523 IOMMU fixes to an isolated porting directory.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
port="$base/vpu-reference-port"
mkdir -p "$port/drivers/iommu" "$port/drivers/clk/sunxi-ng" "$port/include/dt-bindings/reset"
if [ ! -f "$port/STARTED" ]; then
    touch "$port/STARTED"
    cp "$base/linux-7.3.3/drivers/iommu/sun50i-iommu.c" "$port/drivers/iommu/"
    cp "$base/linux-7.3.3/drivers/clk/sunxi-ng/ccu-sun55i-a523.c" "$port/drivers/clk/sunxi-ng/"
    cp "$base/linux-7.3.3/include/dt-bindings/reset/sun55i-a523-ccu.h" "$port/include/dt-bindings/reset/"
fi
for number in 0013 0016 0017 0033 0035 0036 0051 0055; do
    for reference in "$task_root"/upstream/performance-reference/$number-*.patch; do
        patch --batch --fuzz=0 -d "$port" -p1 < "$reference"
    done
done
