#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
artifacts="$task_root/build/pagecheck-kernel"
test -f "$artifacts/BUILD_COMPLETE.json"
test ! -e "$artifacts/linux-entry.bin"
image_bytes=$(stat -c '%s' "$artifacts/Image")
copy_bytes=$(( (image_bytes + 511) / 512 * 512 ))
test "$copy_bytes" -lt 33030144
aarch64-linux-gnu-gcc -static -fno-pie -no-pie -nostdlib -nostartfiles \
    -DTZX_ALIGNED_KERNEL -DTZX_IMAGE_COPY_BYTES=$copy_bytes \
    -Wl,-Ttext=0x4a000000 -Wl,--build-id=none \
    -o "$artifacts/linux-entry.elf" "$task_root/firmware/linux_entry.S"
aarch64-linux-gnu-objcopy -O binary "$artifacts/linux-entry.elf" "$artifacts/linux-entry.bin"
python3 - "$artifacts" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
path = root/'BUILD_COMPLETE.json'
record = json.loads(path.read_text())
record['files']['linux-entry.bin'] = hashlib.sha256((root/'linux-entry.bin').read_bytes()).hexdigest()
path.write_text(json.dumps(record, indent=2)+'\n')
print('PAGECHECK_ALIGNED_ENTRY_BUILT', record['files']['linux-entry.bin'])
PY
