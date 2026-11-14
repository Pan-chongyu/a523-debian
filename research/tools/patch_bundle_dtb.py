"""Update a same-size DTB item after verifying the currently installed bundle header."""
import argparse,hashlib,json,struct,zlib
from flash_linux_probe import ProbeWriter
from fel_device import ROOT,parse_gpt

p=argparse.ArgumentParser()
p.add_argument('--bundle-dir',default='build')
p.add_argument('--output',default='dtb-update.json')
args=p.parse_args()
b=(ROOT/args.bundle_dir).resolve();b.relative_to(ROOT)
manifest = json.loads((b / "linux-bundle.json").read_text())
data = (b / "linux-bundle.bin").read_bytes()
assert len(data)==manifest['bytes'] and hashlib.sha256(data).hexdigest()==manifest['sha256']
header=bytearray(data[:512]);expected_crc=struct.unpack_from('<I',header,16)[0]
struct.pack_into('<I',header,16,0)
assert header[:8]==b'A523BND1' and zlib.crc32(header)==expected_crc
dt = manifest["items"][1]
offset = (dt["lba"] - 4096) * 512
rounded = (dt["bytes"] + 511) & -512
dev = ProbeWriter(manifest["sectors"])
report = {"new_bundle_sha256": manifest["sha256"], "dtb": dt}
try:
    dev.connect()
    report['rtc_before_identity']=dev._read_raw(0x07090100,32).hex()
    report['dram_receipt_before_identity']=dev._read_raw(0x2e000,36).hex()
    report['cpux_watchdog_before_identity']=dev._read_raw(0x02050000,32).hex()
    report['identity']=dev.verify_identity()
    gpt=parse_gpt(dev.read(0,128))
    assert gpt['disk_uuid']=='c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    assert min(item['start'] for item in gpt['partitions'])>=131072
    report['gpt_preserved']=gpt
    previous = dev.read(4096, 1)
    old_header=bytearray(previous);old_crc=struct.unpack_from('<I',old_header,16)[0]
    struct.pack_into('<I',old_header,16,0)
    assert zlib.crc32(old_header)==old_crc
    updated = data[:512]
    # Every placement, size and other payload CRC must be unchanged.
    a, b = bytearray(previous), bytearray(updated)
    a[16:20] = b[16:20] = b"\0" * 4
    a[68:72] = b[68:72] = b"\0" * 4  # item 1 CRC
    if a != b:
        raise RuntimeError("Bundle changed beyond its DTB payload CRC; use the full verified flasher")
    assert struct.unpack_from('<II',updated,56)==(dt['lba'],dt['bytes'])
    assert 4097<=dt['lba'] and dt['lba']+rounded//512<131072
    assert zlib.crc32(data[offset:offset+rounded])==struct.unpack_from('<I',updated,68)[0]
    dev.write_verified(dt["lba"], data[offset:offset + rounded])
    dev.write_verified(4096, updated)
    report["readback"] = "PASS"
    report['verified_changed_bytes']=512+rounded
    dev._write_raw(0x07090110,b'\0'*16)
finally:
    dev.close()
    (ROOT / 'evidence' / args.output).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
