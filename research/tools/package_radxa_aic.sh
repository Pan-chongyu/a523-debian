#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
stage="$base/radxa-aic-package"
mkdir -p "$stage/lib/modules/7.3.3-tzx-a523/extra" "$stage/lib/firmware"
cp "$task_root/build/radxa-aic-modules/aic8800_bsp.ko" "$stage/lib/modules/7.3.3-tzx-a523/extra/"
cp "$task_root/build/radxa-aic-modules/aic8800_fdrv.ko" "$stage/lib/modules/7.3.3-tzx-a523/extra/"
cp "$base/radxa-aic8800/src/SDIO/driver_fw/fw/aic8800D80/"* "$stage/lib/firmware/"
printf '%s\n' 'Candidate SDIO modules and AIC8800D80 firmware; not yet tested on TZX P30.' \
    'Upstream: https://github.com/radxa-pkg/aic8800' \
    'Commit: b6e136a9fe30a4babf0dde5ba9d02313e1c99c30' \
    'Local API port: tools/port_radxa_aic_7.py' > "$stage/ORIGIN.txt"
(cd "$stage" && find lib -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -czf "$task_root/build/radxa-aic-candidate.tar.gz" -C "$stage" .
sha256sum "$task_root/build/radxa-aic-candidate.tar.gz"
