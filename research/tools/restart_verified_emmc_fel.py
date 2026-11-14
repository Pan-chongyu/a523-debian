"""Restart from FEL using the pinned A523 watchdog operation; no storage writes."""
import hashlib
import json
import struct
from fel_device import Device, ROOT, parse_gpt, usb

d = Device(timeout=3000)
record = {'storage_writes': False, 'operation': 'A523 software watchdog reset'}
try:
    d.connect()
    record['rtc_before'] = d._read_raw(0x07090100, 32).hex()
    record['identity'] = d.verify_identity()
    record['gpt'] = parse_gpt(d.read(0, 128))
    assert record['gpt']['disk_uuid'] == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    record['toc0_sha256'] = hashlib.sha256(d.read(256, 80)).hexdigest()
    assert record['toc0_sha256'] == '311c543611e3d1ad497d05acbc43502fdec5df0e06c686a119aae94e775d2a75'
    record['header_sha256'] = hashlib.sha256(d.read(4096, 1)).hexdigest()
    assert record['header_sha256'] == '945f61b5aae262466271cf58574df7d111dfbe800bc27d8a4c5145ae024e707f'
    # A32 word store, matching upstream/xfel/chips/a523_a527_t527.c chip_reset.
    code = struct.pack('<6I', 0xe59f0008, 0xe59f1008, 0xe5801000,
                       0xeafffffe, 0x02050008, 0x16aa0001)
    d._write_raw(0x22000, code)
    assert d._read_raw(0x22000, len(code)) == code
    record['reset_payload_sha256'] = hashlib.sha256(code).hexdigest()
    (ROOT/'evidence/screen-fel-verified-restart.json').write_text(json.dumps(record, indent=2)+'\n')
    try:
        d._exec(0x22000)
    except usb.core.USBError as error:
        record['expected_reset_transport_end'] = str(error)
finally:
    d.close()
    (ROOT/'evidence/screen-fel-verified-restart.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record, indent=2), flush=True)
