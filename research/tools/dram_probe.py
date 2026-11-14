"""Run the fresh LPDDR3 FES1 and verify bounded volatile DRAM pages."""
from pathlib import Path
import hashlib
import json
import struct
import time
from fel_device import Device, ROOT

dev = Device()
report = {"storage_writes": False, "status": "STARTED", "pages": []}
out = ROOT / "evidence/dram-probe.json"
try:
    dev.open_verified()
    report["sid_secure_mode"] = struct.unpack("<I", dev._read_raw(0x030060A0, 4))[0]
    report["sid_rotpk_control"] = struct.unpack("<I", dev._read_raw(0x03006140, 4))[0]
    data = (ROOT / "build/fes1-tzx-lpddr3.bin").read_bytes()
    manifest = json.loads((ROOT / "build/fes1-manifest.json").read_text())
    assert hashlib.sha256(data).hexdigest() == manifest["sha256"]
    dev._write_raw(0x4C000, data)
    assert dev._read_raw(0x4C000, len(data)) == data
    report["status"] = "FES1_UPLOADED"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    dev._exec(0x4C000)
    report["status"] = "FES1_RETURNED"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for address in (0x41000000, 0x60000000, 0x80000000, 0xA0000000):
        original = dev._read_raw(address, 4096)
        try:
            for seed in (0x55, 0xAA):
                pattern = bytes((i * 17 + (i >> 8) + seed) & 255 for i in range(4096))
                dev._write_raw(address, pattern)
                result = dev._read_raw(address, 4096)
                if result != pattern:
                    raise RuntimeError(f"DRAM pattern failed at {address:#x}")
            report["pages"].append({"address": f"0x{address:08x}", "two_patterns": "PASS"})
        finally:
            dev._write_raw(address, original)
            assert dev._read_raw(address, 4096) == original
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["status"] = "VOLATILE_DRAM_PAGES_PASS_CAPACITY_NOT_MEASURED"
except Exception as exc:
    report["error"] = str(exc)
    report["status"] = "FAILED_" + report["status"]
    raise
finally:
    dev.close()
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
