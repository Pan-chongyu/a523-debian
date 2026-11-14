"""Transfer an unchanged file to RAM using acknowledged, CRC-protected records."""
import argparse,hashlib,re,struct,time,zlib
from pathlib import Path
from fel_device import ROOT
import serial
from serial.tools import list_ports
p=argparse.ArgumentParser()
p.add_argument('--file',type=Path,required=True)
p.add_argument('--remote',required=True)
a=p.parse_args()
assert re.fullmatch(r'/tmp/[a-zA-Z0-9_.-]+',a.remote)
size=a.file.stat().st_size
assert 0<size<=512*1024*1024
ports=[p for p in list_ports.comports() if p.vid==0x1d6b and p.pid==0x0104]
assert len(ports)==1
with serial.Serial(ports[0].device,115200,timeout=.1,write_timeout=15) as s:
    s.write(b'\x03\r\n');time.sleep(.3);s.read(s.in_waiting)
    s.write((f'/tmp/usb-receive {a.remote} {size}; '
             f'if [ -x /tmp/fast-sha256 ]; then /tmp/fast-sha256 {a.remote}; '
             f'else sha256sum {a.remote}; fi; echo TZX_RECORD_DONE\n').encode())
    received=bytearray();deadline=time.monotonic()+10
    while b'TZX_RECORD_READY\n' not in received:
        assert time.monotonic()<deadline,repr(received[-1000:])
        received.extend(s.read(4096))
    sha=hashlib.sha256();pos=0;last=time.monotonic();started=last
    with a.file.open('rb') as f:
        while data:=f.read(2048):
            record=struct.pack('<4I',0x43585a54,pos,len(data),zlib.crc32(data))+data
            for retry in range(3):
                s.write(record);ack=bytearray();deadline=time.monotonic()+10
                while len(ack)<8:
                    assert time.monotonic()<deadline,f'ACK timeout at {pos}'
                    ack.extend(s.read(8-len(ack)))
                magic,next_pos=struct.unpack('<II',ack)
                assert magic==0x214b4341,(pos,ack)
                if next_pos==pos+len(data):break
                assert next_pos==pos,(pos,next_pos)
            else:raise RuntimeError(f'Repeated CRC failure at {pos}')
            sha.update(data);pos+=len(data)
            if time.monotonic()-last>=10:
                print(f'USB records: {pos}/{size} bytes, {pos/(time.monotonic()-started)/1048576:.2f} MiB/s',flush=True)
                last=time.monotonic()
    result=bytearray();deadline=time.monotonic()+60
    while b'TZX_RECORD_DONE' not in result and time.monotonic()<deadline:
        result.extend(s.read(4096))
    text=result.decode(errors='replace')
    (ROOT/'evidence'/('transfer-'+Path(a.remote).name+'.txt')).write_text(text,encoding='utf-8')
    assert f'TZX_RECORD_RESULT:0:{size}' in text and sha.hexdigest() in text,text[-2000:]
    print(f'Transferred and verified: {size} bytes, SHA256 {sha.hexdigest()}',flush=True)
