"""Compose a boot-gap bundle from explicitly selected snapshot files."""
import hashlib
import json
import struct
import sys
import zlib
import argparse
from pathlib import Path
from fel_device import ROOT

parser = argparse.ArgumentParser()
parser.add_argument('output')
parser.add_argument('image')
parser.add_argument('dtb')
parser.add_argument('initrd')
parser.add_argument('--entry', default='build/linux-entry.bin')
args = parser.parse_args()
out = ROOT / args.output
items = [
    (ROOT / args.image, 0x48080000),
    (ROOT / args.dtb, 0x47000000),
    (ROOT / args.initrd, 0x60000000),
    (ROOT / args.entry, 0x4A000000),
    (ROOT / "build/bl31.bin", 0x54000),
]
header = bytearray(512)
header[:8] = b"A523BND1"
struct.pack_into("<II", header, 8, 1, len(items))
bundle = bytearray(512)
lba = 4097
manifest = {"start_lba": 4096, "items": [], "hardware_boot_verified": False}
for path, address in items:
    data = path.read_bytes()
    padded = data + b"\0" * (-len(data) % 512)
    struct.pack_into("<6I", header, 32 + len(manifest["items"]) * 24,
                     lba, len(data), address, zlib.crc32(padded), 0, 0)
    manifest["items"].append({"file": path.name, "lba": lba, "bytes": len(data),
                               "load_address": hex(address),
                               "sha256": hashlib.sha256(data).hexdigest()})
    bundle.extend(padded)
    lba += len(padded) // 512
struct.pack_into("<I", header, 16, zlib.crc32(header))
bundle[:512] = header
manifest.update(bytes=len(bundle), sectors=len(bundle) // 512,
                sha256=hashlib.sha256(bundle).hexdigest())
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(bundle)
out.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
print(json.dumps(manifest, indent=2))
