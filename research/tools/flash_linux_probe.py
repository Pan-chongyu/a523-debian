"""Write and fully read back the fresh Linux probe, then its TOC0 entries.

No reset is performed. The owner authorized overwriting this exact eMMC.
"""
import hashlib
import argparse
import json
import struct
import time
from fel_device import Device, ROOT, parse_gpt


class ProbeWriter(Device):
    def __init__(self, bundle_sectors):
        super().__init__()
        self.bundle_end = 4096 + bundle_sectors

    def _run_helper(self, operation, sector, count):
        if operation != 2:
            return super()._run_helper(operation, sector, count)
        allowed = (4096 <= sector and sector + count <= self.bundle_end) or (
            sector == 256 and count <= 128)
        if not self.identity_verified or not allowed or not 0 < count <= 128:
            raise RuntimeError("Write outside the fresh probe's exact windows")
        self._write_raw(0x2FFF0, struct.pack("<IIII", 2, sector, count, 0))
        self._write_raw(0x07090100, struct.pack("<I", 1))
        self._exec(0x20000)
        for _ in range(160):
            state = struct.unpack("<I", self._read_raw(0x07090100, 4))[0]
            if state == 0xAA:
                return
            if state == 0xEE:
                raise RuntimeError("Write failed: " + self._read_raw(0x07090100, 16).hex())
            time.sleep(0.05)
        raise TimeoutError("Probe write did not finish")

    def write_verified(self, lba, data):
        if not data or len(data) % 512 or len(data) > 65536:
            raise ValueError("Expected 1..128 whole sectors")
        self._write_raw(0x30000, data)
        if self._read_raw(0x30000, len(data)) != data:
            raise RuntimeError("SRAM staging verification failed")
        self._run_helper(2, lba, len(data) // 512)
        if self.read(lba, len(data) // 512) != data:
            raise RuntimeError(f"eMMC readback differs at LBA {lba}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Read and retain identical existing chunks")
    parser.add_argument("--bundle-dir", type=str, default="build",
                        help="Directory containing a matching bundle and manifest; TOC0 stays in build")
    args = parser.parse_args()
    bundle_dir = (ROOT / args.bundle_dir).resolve()
    bundle_dir.relative_to(ROOT.resolve())
    bundle = (bundle_dir / "linux-bundle.bin").read_bytes()
    bm = json.loads((bundle_dir / "linux-bundle.json").read_text())
    toc = (ROOT / "build/chain-loader.toc0").read_bytes()
    tm = json.loads((ROOT / "build/chain-loader.toc0.json").read_text())
    assert len(bundle) == bm["bytes"] and hashlib.sha256(bundle).hexdigest() == bm["sha256"]
    assert 0 < len(toc) <= 65536 and hashlib.sha256(toc).hexdigest() == tm["image_sha256"]
    assert bundle[:8] == b"A523BND1" and toc[:8] == b"TOC0.GLH"
    dev = ProbeWriter(len(bundle) // 512)
    path = ROOT / "evidence/linux-probe-flash.json"
    report = {"bundle_directory": str(bundle_dir), "bundle_sha256": bm["sha256"], "toc0_sha256": tm["image_sha256"],
              "verified_bundle_bytes": 0, "toc0_slots": [], "reset": False}
    def save():
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        dev.connect()
        report["rtc_before_identity"] = dev._read_raw(0x07090100, 32).hex()
        report["identity"] = dev.verify_identity()
        disk_head=dev.read(0,128)
        if disk_head[512:520]==b"EFI PART":
            existing=parse_gpt(disk_head)
            assert existing['disk_uuid']=='c9a3ed89-a30d-4fbc-ba53-208fa8617cbc', 'Unknown GPT; refusing'
            assert min(p['start'] for p in existing['partitions'])>=131072, 'Partitions overlap boot gap'
            slots=(256,)
            report['gpt_preserved']=existing
        else:
            raise RuntimeError('Expected the installed Debian GPT; refusing an unknown disk layout')
        save()
        for offset in range(0, len(bundle), 65536):
            data = bundle[offset:offset + 65536]
            report["write_intent_lba"] = 4096 + offset // 512
            save()
            if not args.resume or dev.read(report["write_intent_lba"], len(data) // 512) != data:
                dev.write_verified(report["write_intent_lba"], data)
            report["verified_bundle_bytes"] = offset + len(data)
            save()
            if offset % 1048576 == 0:
                print(f"Bundle verified: {offset + len(data)}/{len(bundle)} bytes", flush=True)
        # Commit the new boot stage only once every bundle byte is verified.
        for lba in slots:
            report["write_intent_lba"] = lba
            save()
            dev.write_verified(lba, toc)
            report["toc0_slots"].append({"lba": lba, "readback": "PASS"})
            save()
        dev._write_raw(0x07090110, b"\0" * 12)
        report["status"] = "LINUX_PROBE_WRITTEN_AND_VERIFIED_UNBOOTED"
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        dev.close()
        save()
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
