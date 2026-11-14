"""Exercise the exact cold-loader read path without writing eMMC or DRAM."""
import argparse,hashlib,json,struct,time
from fel_device import Device,ROOT,parse_gpt

p=argparse.ArgumentParser()
p.add_argument('--bundle-dir',default='build')
p.add_argument('--reader',default='fel-checked-reader')
p.add_argument('--output',default='fifo-reader-fel-verification.json')
a=p.parse_args()
assert a.reader in ('fel-checked-reader','fel-retry-reader')
bundle_dir=(ROOT/a.bundle_dir).resolve();bundle_dir.relative_to(ROOT)
data=(bundle_dir/'linux-bundle.bin').read_bytes()
assert len(data)%512==0
binary=(ROOT/'build'/f'{a.reader}.bin').read_bytes()
elf=(ROOT/'build'/f'{a.reader}.elf').read_bytes()
entry=struct.unpack_from('<I',elf,24)[0]
assert 0x20000<=entry<0x20000+len(binary)<0x28000
d=Device(timeout=15000);report={'test':a.reader+', SRAM only',
    'emmc_writes':False,'dram_writes':False,'reader_sha256':hashlib.sha256(binary).hexdigest(),
    'entry':hex(entry),'verified_bytes':0}
path=ROOT/'evidence'/a.output
def save():path.write_text(json.dumps(report,indent=2),encoding='utf8')
try:
    d.connect();report['rtc_before_identity']=d._read_raw(0x07090100,32).hex()
    report['identity']=d.verify_identity()
    gpt=parse_gpt(d.read(0,128));assert gpt['disk_uuid']=='c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
    d._write_raw(0x20000,binary);assert d._read_raw(0x20000,len(binary))==binary
    start=time.monotonic()
    for offset in range(0,len(data),65536):
        expected=data[offset:offset+65536];count=len(expected)//512
        d._write_raw(0x2fff0,struct.pack('<4I',1,4096+offset//512,count,int(offset!=0)))
        d._write_raw(0x07090100,struct.pack('<I',1))
        d._exec(entry)
        state=struct.unpack('<8I',d._read_raw(0x07090100,32))
        if state[0]!=0xaa:raise RuntimeError('Reader status: '+','.join(hex(x) for x in state))
        actual=d._read_raw(0x30000,len(expected))
        if actual!=expected:raise RuntimeError(f'Data mismatch at bundle offset {offset}')
        report['verified_bytes']=offset+len(actual);save()
        if offset%1048576==0:print(f"Verified {report['verified_bytes']}/{len(data)} bytes",flush=True)
    report.update(result='PASS',seconds=round(time.monotonic()-start,3),
        bundle_sha256=hashlib.sha256(data).hexdigest())
except Exception as e:
    report.update(result='FAIL',error=str(e));raise
finally:
    save();d.close();print(json.dumps(report,indent=2),flush=True)
