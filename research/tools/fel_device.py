"""Fresh native Windows FEL transport, based on the upstream XFEL protocol.

Uses PyUSB/libusb from PyPI and a freshly compiled upstream A523-root helper.
The command-line interface only reads storage and never resets the device.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import time
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python-deps"))
import usb.core
import usb.util
import libusb_package
HELPER = ROOT / "upstream/A523-root/tools/fel-emmc.bin"
EXPECTED_CID = "3e01ff55454d20202010209170281b59"
CAPACITY = 244318208


def identity(info):
    if len(info) != 528:
        raise RuntimeError("Short eMMC identity")
    cid = info[:16][::-1].hex()
    sectors = struct.unpack_from("<I", info, 16 + 212)[0]
    partition_config = info[16 + 179]
    if cid != EXPECTED_CID or sectors != CAPACITY or partition_config & 7:
        raise RuntimeError(f"Wrong target: {cid=}, {sectors=}, {partition_config=}")
    return {"cid": cid, "sectors": sectors, "bytes": sectors * 512,
            "partition_config": partition_config, "boot_size_bytes": info[16 + 226] * 131072}


class Device:
    def __init__(self, timeout=10000):
        self.usb = None
        self.timeout = timeout
        self.identity_verified = False
        self.identity_bytes = None
        self.endpoint_in = self.endpoint_out = None

    def _send(self, data):
        for offset in range(0, len(data), 131072):
            chunk = data[offset:offset + 131072]
            if self.usb.write(self.endpoint_out, chunk, timeout=self.timeout) != len(chunk):
                raise RuntimeError("Short USB write")

    def _receive(self, length):
        result = bytearray()
        while len(result) < length:
            chunk = self.usb.read(self.endpoint_in, min(length - len(result), 131072), timeout=self.timeout)
            if not len(chunk):
                raise RuntimeError("Empty USB read")
            result.extend(chunk)
        return bytes(result)

    def _usb_request(self, operation, length):
        packet = bytearray(32)
        packet[:4] = b"AWUC"
        struct.pack_into("<IIHI", packet, 8, length, 0x0C000000, operation, length)
        self._send(packet)

    def _ack(self):
        data = self._receive(13)
        signature, tag, residue, state = struct.unpack("<4sIIB", data)
        if signature != b"AWUS" or tag or residue or state:
            raise RuntimeError(f"USB acknowledgement failed: {data.hex()}")

    def _usb_write(self, data):
        self._usb_request(0x12, len(data))
        self._send(data)
        self._ack()

    def _usb_read(self, length):
        self._usb_request(0x11, length)
        result = self._receive(length)
        self._ack()
        return result

    def _request(self, operation, address=0, length=0):
        self._usb_write(struct.pack("<IIII", operation, address, length, 0))

    def _status(self):
        data = self._usb_read(8)
        if data[:2] == b"\xff\xff" and data[4] != 0:
            raise RuntimeError(f"FEL status failed: {data.hex()}")

    def _write_raw(self, address, data):
        self._request(0x101, address, len(data))
        self._usb_write(data)
        self._status()

    def _read_raw(self, address, length):
        self._request(0x103, address, length)
        result = self._usb_read(length)
        self._status()
        return result

    def _exec(self, address):
        self._request(0x102, address)
        self._status()

    def connect(self):
        devices = list(libusb_package.find(find_all=True, idVendor=0x1F3A, idProduct=0xEFE8))
        if len(devices) != 1:
            raise RuntimeError(f"Expected one FEL device, found {len(devices)}")
        self.usb = devices[0]
        usb.util.claim_interface(self.usb, 0)
        interface = self.usb.get_active_configuration()[(0, 0)]
        for ep in interface:
            if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK:
                if ep.bEndpointAddress & 0x80:
                    self.endpoint_in = ep.bEndpointAddress
                else:
                    self.endpoint_out = ep.bEndpointAddress
        if self.endpoint_in is None or self.endpoint_out is None:
            raise RuntimeError("Missing FEL bulk endpoints")
        self._request(1)
        version = self._usb_read(32)
        self._status()
        if version[:8] != b"AWUSBFEX" or struct.unpack_from("<I", version, 8)[0] != 0x00189000:
            raise RuntimeError(f"Wrong chip: {version.hex()}")
        helper = HELPER.read_bytes()
        if not (0 < len(helper) < 32768):
            raise RuntimeError("Invalid SRAM helper size")
        self._write_raw(0x20000, helper)
        if self._read_raw(0x20000, len(helper)) != helper:
            raise RuntimeError("SRAM helper verification failed")
        print(json.dumps({"fel_version": version.hex(), "helper_sha256": hashlib.sha256(helper).hexdigest()}), flush=True)

    def verify_identity(self):
        self._run_helper(3, 0, 0)
        info = self._read_raw(0x30000, 528)
        card = identity(info)
        self.identity_bytes = info
        self.identity_verified = True
        return card

    def close(self):
        if self.usb is not None:
            usb.util.dispose_resources(self.usb)
            self.usb = None

    def _in_read_fence(self, sector, count):
        return 0 <= sector < CAPACITY and 0 < count <= 128 and sector + count <= CAPACITY

    def _run_helper(self, operation, sector, count):
        if operation == 3:
            assert sector == count == 0
        elif operation == 1:
            if not self.identity_verified or not self._in_read_fence(sector, count):
                raise RuntimeError("Unverified target or invalid read range")
        else:
            raise RuntimeError("This transport only permits eMMC READ and INFO")
        self._write_raw(0x2FFF0, struct.pack("<IIII", operation, sector, count, 0))
        self._write_raw(0x07090100, struct.pack("<I", 1))
        if self._read_raw(0x07090100, 4) != struct.pack("<I", 1):
            raise RuntimeError("Completion sentinel did not read back")
        self._exec(0x20000)
        for _ in range(120):
            status = struct.unpack("<I", self._read_raw(0x07090100, 4))[0]
            if status == 0xAA:
                return
            if status == 0xEE:
                raise RuntimeError(f"eMMC helper failed: {self._read_raw(0x07090100, 16).hex()}")
            time.sleep(0.05)
        raise TimeoutError("eMMC helper did not complete")

    def open_verified(self):
        self.connect()
        return self.verify_identity()

    def read(self, sector, count):
        result = bytearray()
        for offset in range(0, count, 128):
            chunk = min(128, count - offset)
            self._run_helper(1, sector + offset, chunk)
            result.extend(self._read_raw(0x30000, chunk * 512))
        return bytes(result)


def parse_gpt(head):
    hdr = bytearray(head[512:1024])
    if hdr[:8] != b"EFI PART":
        raise RuntimeError("Missing GPT signature")
    length, checksum = struct.unpack_from("<II", hdr, 12)
    struct.pack_into("<I", hdr, 16, 0)
    if zlib.crc32(hdr[:length]) != checksum:
        raise RuntimeError("GPT header CRC mismatch")
    entries_lba, entries, stride, table_crc = struct.unpack_from("<QIII", hdr, 72)
    table = head[entries_lba * 512:entries_lba * 512 + entries * stride]
    if len(table) != entries * stride or zlib.crc32(table) != table_crc:
        raise RuntimeError("GPT entries CRC mismatch or insufficient capture")
    partitions = []
    for n in range(entries):
        entry = table[n * stride:(n + 1) * stride]
        if not any(entry[:16]):
            continue
        start, end, attrs = struct.unpack_from("<QQQ", entry, 32)
        partitions.append({"number": n + 1, "name": entry[56:128].decode("utf-16-le").rstrip("\0"),
                           "start": start, "sectors": end - start + 1,
                           "uuid": str(uuid.UUID(bytes_le=entry[16:32]))})
    return {"disk_uuid": str(uuid.UUID(bytes_le=bytes(hdr[56:72]))), "partitions": partitions}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["probe", "read"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sector", type=int)
    parser.add_argument("--count", type=int)
    args = parser.parse_args()
    dev = Device()
    try:
        card = dev.open_verified()
        if args.action == "probe":
            args.output.mkdir(parents=True, exist_ok=True)
            head = dev.read(0, 128)
            tail = dev.read(CAPACITY - 33, 33)
            (args.output / "gpt-head.bin").write_bytes(head)
            (args.output / "gpt-tail.bin").write_bytes(tail)
            (args.output / "emmc-info.bin").write_bytes(dev.identity_bytes)
            report = {"card": card, "gpt": parse_gpt(head),
                      "toc1_headers": {str(lba): dev.read(lba, 1)[:96].hex() for lba in (24576, 32800)},
                      "storage_writes": False}
            (args.output / "device.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2), flush=True)
        else:
            if args.sector is None or args.count is None or args.count <= 0:
                parser.error("read requires --sector and positive --count")
            data = dev.read(args.sector, args.count)
            args.output.write_bytes(data)
            print(json.dumps({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}))
    finally:
        dev.close()


if __name__ == "__main__":
    main()
