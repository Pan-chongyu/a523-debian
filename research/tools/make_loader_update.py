"""Build a CID- and SHA-guarded update for the single TOC0 boot-gap slot."""
from pathlib import Path
import hashlib
from fel_device import ROOT, EXPECTED_CID

p=ROOT/'build/chain-diagnostic.toc0'
data=p.read_bytes()
assert data[:8]==b'TOC0.GLH' and 0<len(data)<=65536 and len(data)%512==0
digest=hashlib.sha256(data).hexdigest()
script=f'''#!/bin/sh
set -eu
test "$(cat /sys/class/block/mmcblk0/device/cid)" = '{EXPECTED_CID}'
test "$(sha256sum /home/debian/chain-diagnostic.toc0 | cut -d ' ' -f1)" = '{digest}'
dd if=/home/debian/chain-diagnostic.toc0 of=/dev/mmcblk0 bs=512 seek=256 conv=fsync status=none
actual=$(dd if=/dev/mmcblk0 bs=512 skip=256 count={len(data)//512} status=none | sha256sum | cut -d ' ' -f1)
test "$actual" = '{digest}'
echo TOC0_FULL_READBACK_PASS:$actual
sync
'''
(ROOT/'build/update-diagnostic-loader.sh').write_text(script,encoding='ascii',newline='\n')
print(digest)
