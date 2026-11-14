"""Build an A523 two-item TOC0 with a new local RSA key and fresh firmware.

The certificate layout and board data are taken from this device's freshly
read TOC0 descriptor. No firmware from that descriptor is included. This ROM
uses raw RSA over SHA256(TBS excluding its last four bytes), verified against
the device's certificate before generating anything.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fel_device import ROOT


def digest(data):
    return hashlib.sha256(data).digest()


def build(firmware, load_address, output):
    original = (ROOT / "evidence/initial-fel/toc0-descriptor.bin").read_bytes()
    cert = bytearray(original[0xC80:0xF80])
    assert len(cert) == 768 and cert[:8] == bytes.fromhex("308202fc308201e3")
    public_n = int.from_bytes(cert[178:434], "big")
    public_e = int.from_bytes(cert[436:439], "big")
    recovered = pow(int.from_bytes(cert[-256:], "big"), public_e, public_n)
    assert recovered == int.from_bytes(digest(cert[4:487]), "big")
    assert cert[445:477] == digest(original[0xF80:0x17F80])

    key_path = ROOT / "private/boot-signing.pem"
    key_path.parent.mkdir(exist_ok=True)
    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()))
    numbers = key.private_numbers()
    firmware = firmware + b"\0" * (-len(firmware) % 32)
    cert[178:434] = numbers.public_numbers.n.to_bytes(256, "big")
    cert[445:477] = digest(firmware)
    hashed = int.from_bytes(digest(cert[4:487]), "big")
    cert[-256:] = pow(hashed, numbers.d, numbers.public_numbers.n).to_bytes(256, "big")
    assert pow(int.from_bytes(cert[-256:], "big"), 65537, numbers.public_numbers.n) == hashed

    length = (0xF80 + len(firmware) + 8191) & -8192
    image = bytearray(length)
    # Header, item directory, and the board's non-executable configuration.
    image[:0xC80] = original[:0xC80]
    struct.pack_into("<I", image, 0x1C, length)
    struct.pack_into("<II", image, 0x54, 0xF80, len(firmware))
    struct.pack_into("<I", image, 0x64, load_address)
    image[0xC80:0xF80] = cert
    image[0xF80:0xF80 + len(firmware)] = firmware
    struct.pack_into("<I", image, 0x0C, 0x5F0A6C39)
    checksum = sum(struct.unpack(f"<{length // 4}I", image)) & 0xFFFFFFFF
    struct.pack_into("<I", image, 0x0C, checksum)
    check = sum(struct.unpack(f"<{length // 4}I", image)) & 0xFFFFFFFF
    assert (check + 0x5F0A6C39 - 2 * checksum) & 0xFFFFFFFF == 0
    output.write_bytes(image)
    report = {"image_sha256": digest(image).hex(), "image_bytes": length,
              "firmware_sha256": digest(firmware).hex(), "firmware_bytes": len(firmware),
              "load_address": hex(load_address), "new_key": True,
              "signature": "A523 raw RSA-2048 SHA256, TBS length excludes last four bytes",
              "device_certificate_verified": True,
              "reused_executable_bytes": 0}
    output.with_suffix(output.suffix + ".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--load", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.firmware.read_bytes(), args.load, args.output)
