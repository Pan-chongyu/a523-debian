"""Flash a freshly signed, at-most-64-KiB probe into the two TOC0 slots.

The owner explicitly authorized destructive eMMC testing and no system backup.
This does not reset the device. Both TOC0 writes must pass complete readback.
"""
import hashlib
import argparse
import json
import struct
import time
from fel_device import Device, ROOT


class Writer(Device):
    def _run_helper(self, operation, sector, count):
        if operation != 2:
            return super()._run_helper(operation, sector, count)
        if not self.identity_verified or not 0 < count <= 128 or sector not in (16, 256):
            raise RuntimeError("Only the two at-most-128-sector TOC0 probe windows are permitted")
        self._write_raw(0x2FFF0, struct.pack("<IIII", operation, sector, count, 0))
        self._write_raw(0x07090100, struct.pack("<I", 1))
        assert self._read_raw(0x07090100, 4) == struct.pack("<I", 1)
        self._exec(0x20000)
        for _ in range(120):
            status = struct.unpack("<I", self._read_raw(0x07090100, 4))[0]
            if status == 0xAA:
                return
            if status == 0xEE:
                raise RuntimeError(f"TOC0 write failed: {self._read_raw(0x07090100, 16).hex()}")
            time.sleep(0.05)
        raise TimeoutError("TOC0 write timed out")


dev = Writer()
parser = argparse.ArgumentParser()
parser.add_argument("--image", default="cold-marker.toc0")
parser.add_argument("--report", default="cold-marker-flash.json")
args = parser.parse_args()
assert args.image in ("cold-marker.toc0", "cold-dram.toc0")
image = (ROOT / "build" / args.image).read_bytes()
assert image[:8] == b"TOC0.GLH" and 0 < len(image) <= 65536 and len(image) % 512 == 0
manifest = json.loads((ROOT / "build" / (args.image + ".json")).read_text(encoding="utf-8"))
assert manifest["image_sha256"] == hashlib.sha256(image).hexdigest()
assert manifest["load_address"] == "0x44000" and manifest["reused_executable_bytes"] == 0
report = {"image_sha256": hashlib.sha256(image).hexdigest(), "writes": [], "reset": False}
path = ROOT / "evidence" / args.report
try:
    report["identity"] = dev.open_verified()
    for sector in (256, 16):
        dev._write_raw(0x30000, image)
        assert dev._read_raw(0x30000, len(image)) == image
        report["write_intent_lba"] = sector
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        dev._run_helper(2, sector, len(image) // 512)
        readback = dev.read(sector, len(image) // 512)
        if readback != image:
            raise RuntimeError(f"TOC0 full readback differs at LBA {sector}")
        report["writes"].append({"lba": sector, "sectors": len(image) // 512, "readback": "PASS"})
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Distinguishes the new cold-boot marker from earlier RTC contents.
    dev._write_raw(0x07090110, b"\0" * 12)
    assert dev._read_raw(0x07090110, 12) == b"\0" * 12
    report["status"] = "SIGNED_PROBE_WRITTEN_AND_VERIFIED_UNBOOTED"
finally:
    dev.close()
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
