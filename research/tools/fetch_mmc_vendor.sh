#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
repository=/opt/a523-debian-20261109/avaota-linux
commit=a464bc4feaff7b102dac6362b44ac3303ec7cae1
out="$task_root/upstream/mmc-vendor"
mkdir -p "$out"
for path in bsp/drivers/mmc/sunxi-mmc-v4p5x.c bsp/drivers/mmc/sunxi-mmc-v5p3x.c \
    bsp/drivers/mmc/sunxi-mmc-v5p3x-HS400-phase-delaychain.c bsp/drivers/mmc/sunxi-mmc.c \
    bsp/drivers/mmc/sunxi-mmc.h; do
    git -C "$repository" show "$commit:$path" > "$out/$(basename "$path")"
done
git -C "$repository" ls-tree -r "$commit" bsp/drivers/mmc > "$out/TREE.txt"
printf '%s\n' "$commit" > "$out/COMMIT.txt"
sha256sum "$out/"*.c "$out/"*.h
