"""Create a fresh GPT for only the explicitly identified 244318208-sector eMMC."""
import json
import struct
import uuid
import zlib
from fel_device import ROOT, CAPACITY, EXPECTED_CID

build = ROOT / "build"
disk_guid = uuid.uuid4()
parts = [("DEBIAN_BOOT", 131072, 1048576, "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"),
         ("DEBIAN_ROOT", 1179648, CAPACITY - 33 - 1179648, "0fc63daf-8483-4772-8e79-3d69d8477de4")]
table = bytearray(16384)
manifest = {"cid": EXPECTED_CID, "sectors": CAPACITY, "disk_uuid": str(disk_guid), "partitions": []}
for i, (name, first, count, type_id) in enumerate(parts):
    part_guid = uuid.uuid4()
    off = i * 128
    table[off:off + 16] = uuid.UUID(type_id).bytes_le
    table[off + 16:off + 32] = part_guid.bytes_le
    struct.pack_into("<QQQ", table, off + 32, first, first + count - 1, 0)
    table[off + 56:off + 56 + len(name) * 2] = name.encode("utf-16-le")
    manifest["partitions"].append({"name": name, "start": first, "sectors": count, "uuid": str(part_guid)})

def header(lba, other, table_lba):
    h = bytearray(512)
    h[:8] = b"EFI PART"
    struct.pack_into("<IIIIQQQQ", h, 8, 0x10000, 92, 0, 0, lba, other, 2048, CAPACITY - 34)
    h[56:72] = disk_guid.bytes_le
    struct.pack_into("<QIII", h, 72, table_lba, 128, 128, zlib.crc32(table))
    struct.pack_into("<I", h, 16, zlib.crc32(h[:92]))
    return h

mbr = bytearray(512)
mbr[446:462] = b"\0\0\x02\0\xee\xff\xff\xff" + struct.pack("<II", 1, CAPACITY - 1)
mbr[510:] = b"\x55\xaa"
(build / "gpt-primary.bin").write_bytes(mbr + header(1, CAPACITY - 1, 2) + table)
(build / "gpt-backup.bin").write_bytes(table + header(CAPACITY - 1, 1, CAPACITY - 33))
(build / "install-layout.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
