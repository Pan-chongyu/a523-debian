"""Freeze the matching source, ELF and signed retry-loader payload."""
import hashlib,json,shutil,struct
from fel_device import ROOT
out=ROOT/'build/chain-retry-snapshot'
assert not out.exists()
raw=(ROOT/'build/chain-retry.bin').read_bytes()
toc=(ROOT/'build/chain-retry.toc0').read_bytes()
manifest=json.loads((ROOT/'build/chain-retry.toc0.json').read_text())
assert hashlib.sha256(toc).hexdigest()==manifest['image_sha256']
padded=raw+b'\0'*(-len(raw)%32)
assert toc[0xf80:0xf80+len(padded)]==padded
assert hashlib.sha256(padded).hexdigest()==manifest['firmware_sha256']
assert struct.unpack_from('<I',(ROOT/'build/chain-retry.elf').read_bytes(),24)[0]==0x44000
items=['firmware/cold_retry_entry.S','firmware/chain_retry_loader.c','firmware/emmc_retry_reader.c',
       'firmware/dram_probe.c','firmware/dram.ld','firmware/enter_arm64.S','tools/build_retry_loader.sh',
       'build/dram_params.h','build/chain-retry.bin','build/chain-retry.elf','build/chain-retry.map',
       'build/chain-retry.toc0','build/chain-retry.toc0.json','evidence/retry-loader-host-verification.json']
report={}
for name in items:
    data=(ROOT/name).read_bytes();dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/name,dest)
    report[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
(out/'snapshot.json').write_text(json.dumps({'hardware_boot_verified':False,'artifacts':report},indent=2),encoding='utf8')
print('Frozen source/ELF/TOC0 payload match:',manifest['image_sha256'])
