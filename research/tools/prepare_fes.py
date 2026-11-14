"""Create a board-specific volatile DRAM initializer from fresh upstream XFEL.

Only DRAM parameters measured from this device are carried across. No existing
OS, old project binary, or old project configuration is an input.
"""
from pathlib import Path
import hashlib
import json
import re
import struct

root = Path(__file__).resolve().parents[1]
source = root / "upstream/xfel/chips/a523_a527_t527.c"
array = source.read_text().split("lpddr4_payload [] = {", 1)[1].split("};", 1)[0]
payload = bytearray(int(s, 16) for s in re.findall(r"0x([0-9a-fA-F]{2})", array))
descriptor = (root / "evidence/initial-fel/toc0-descriptor.bin").read_bytes()
assert descriptor[:8] == b"TOC0.GLH"
parameters = descriptor[0x84:0x104]
values = struct.unpack("<32I", parameters)
assert values[0:2] == (936, 7), "Device must supply its LPDDR3 parameters"
assert payload[4:12] == b"eGON.BT0"
assert struct.unpack_from("<I", payload, 0x3C)[0] == 8, "Unexpected upstream FES1 layout"
assert struct.unpack_from("<I", payload, 0x10)[0] == len(payload)
payload[0x38:0xB8] = parameters
struct.pack_into("<I", payload, 0x0C, 0x5F0A6C39)
checksum = sum(struct.unpack(f"<{len(payload)//4}I", payload)) & 0xFFFFFFFF
struct.pack_into("<I", payload, 0x0C, checksum)
build = root / "build"
build.mkdir(exist_ok=True)
output = build / "fes1-tzx-lpddr3.bin"
output.write_bytes(payload)
manifest = {"source": "https://github.com/xboot/xfel", "upstream_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "parameter_source": "fresh FEL read of device TOC0 descriptor at LBA 16",
            "dram_type": "LPDDR3", "clock_mhz": values[0], "parameters": [f"0x{v:08x}" for v in values],
            "load_address": "0x0004c000", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "hardware_tested": False, "storage_writes": False}
(build / "fes1-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
