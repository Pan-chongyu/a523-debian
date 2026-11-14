"""Assemble the five freshly built images for the SRAM eMMC loader."""
import hashlib
import json
import struct
import subprocess
import zlib
from fel_device import ROOT

build = ROOT / "build"
initrd = (build / "initramfs.cpio.gz").read_bytes()
dtb_wsl = "/mnt/c/Users/pan75/Documents/ChatGPT/A523适配debian/build/board.dtb"
subprocess.run(["wsl", "-d", "Ubuntu-22.04", "--", "fdtput", "-t", "x", dtb_wsl,
                "/chosen", "linux,initrd-end", "0", f"{0x60000000 + len(initrd):x}"], check=True)
items = [("Image", 0x48080000), ("board.dtb", 0x47000000),
         ("initramfs.cpio.gz", 0x60000000), ("linux-entry.bin", 0x4A000000),
         ("bl31.bin", 0x54000)]
assert (build / "Image").read_bytes()[0x38:0x3C] == b"ARM\x64"
header = bytearray(512)
header[:8] = b"A523BND1"
struct.pack_into("<II", header, 8, 1, len(items))
bundle = bytearray(512)
lba = 4097
manifest = {"start_lba": 4096, "items": [], "hardware_boot_verified": False}
for i, (name, address) in enumerate(items):
    data = (build / name).read_bytes()
    rounded = data + b"\0" * (-len(data) % 512)
    struct.pack_into("<6I", header, 32 + i * 24, lba, len(data), address,
                     zlib.crc32(rounded), 0, 0)
    manifest["items"].append({"file": name, "lba": lba, "bytes": len(data),
                               "load_address": hex(address), "sha256": hashlib.sha256(data).hexdigest()})
    lba += len(rounded) // 512
    bundle.extend(rounded)
assert lba < 131072, "Bundle must remain below the future boot partition"
struct.pack_into("<I", header, 16, zlib.crc32(header))
bundle[:512] = header
(build / "linux-bundle.bin").write_bytes(bundle)
manifest.update(bytes=len(bundle), sectors=len(bundle) // 512, sha256=hashlib.sha256(bundle).hexdigest())
(build / "linux-bundle.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
