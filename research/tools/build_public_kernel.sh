#!/bin/sh
set -eu
base=/opt/a523-debian-20261109
task=/opt/a523-public-release
src="$task/working/linux-7.3.3"
out="$task/working/kernel-build"
test ! -e "$src"
cp -a "$base/linux-hs-source" "$src"
mkdir -p "$out"
cp "$base/kernel-hs-build/.config" "$out/.config"
python3 - "$src/drivers/mmc/host/tzx_emmc_host.inc" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
assert s.count('memcmp(card->raw_cid,cid,sizeof(cid))')==1
s=s.replace('memcmp(card->raw_cid,cid,sizeof(cid))','memcmp(card->raw_cid,cid,2*sizeof(u32))')
p.write_text(s)
PY
make -C "$src" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig > "$task/kernel-build.log" 2>&1
make -C "$src" O="$out" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    KBUILD_BUILD_VERSION=5 KBUILD_BUILD_USER=builder KBUILD_BUILD_HOST=a523-debian \
    -j8 Image modules >> "$task/kernel-build.log" 2>&1
cp "$out/arch/arm64/boot/Image" "$task/assets/Image"
sha256sum "$task/assets/Image"
echo PUBLIC_KERNEL_BUILD_COMPLETE
