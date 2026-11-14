"""Load candidate firmware into volatile touch SRAM, then remove test power."""
import ctypes as C, errno, hashlib, os, struct, subprocess, sys, time
from pathlib import Path

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
blob=Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(blob).hexdigest()==sys.argv[2] and len(blob)%8==0
class Msg(C.Structure):
    _fields_=[('addr',C.c_uint16),('flags',C.c_uint16),('length',C.c_uint16),('buf',C.c_void_p)]
class Transfer(C.Structure):
    _fields_=[('msgs',C.POINTER(Msg)),('count',C.c_uint32)]
libc=C.CDLL(None,use_errno=True)
def ioctl(fd,cmd,arg):
    if libc.ioctl(fd,cmd,arg)<0:
        raise OSError(C.get_errno(),os.strerror(C.get_errno()))
class Bus:
    def __init__(self,bus,addr):
        self.fd=os.open('/dev/i2c-'+str(bus),os.O_RDWR);self.addr=addr
        ioctl(self.fd,0x703,addr)
    def write(self,reg,data):
        packet=bytes([reg])+bytes(data)
        for attempt in range(10):
            try:
                assert os.write(self.fd,packet)==len(packet)
                return
            except OSError as error:
                if error.errno!=errno.EAGAIN or attempt==9:raise
                time.sleep(0.01)
    def read(self,reg,length):
        tx=C.create_string_buffer(bytes([reg]));rx=C.create_string_buffer(length)
        msgs=(Msg*2)(Msg(self.addr,0,1,C.addressof(tx)),Msg(self.addr,1,length,C.addressof(rx)))
        transfer=Transfer(msgs,2);ioctl(self.fd,0x707,C.byref(transfer));return rx.raw
pmic=None if '--powered' in sys.argv[3:] else Bus(0,0x34)
ts=Bus(1,0x40)
if pmic:
    assert pmic.read(0x91,1)==b'\xd5' and pmic.read(0x9c,1)==b'\x1c'
probe=None
try:
    if pmic:pmic.write(0x91,b'\xd7')
    probe=subprocess.Popen(['/home/debian/peripheral-gpio-probe','touch','--interactive'],stdin=subprocess.PIPE)
    time.sleep(0.3)
    print('CHIP_ID',ts.read(0xfc,4).hex(),flush=True)
    # The current GSL3670 startup sequence uses register 0x88, rather than
    # the older GSL1680 reset command 0xe0=0x88 which this chip rejects.
    for reg,val in [(0x88,1),(0xe4,4),(0xe0,0),(0xe4,4),(0xbc,0)]:
        if reg==0xbc:
            probe.stdin.write(b'r');probe.stdin.flush();time.sleep(0.1)
            ts.write(0xe4,[4]);time.sleep(0.015)
        print('INIT',hex(reg),hex(val),flush=True)
        ts.write(reg,struct.pack('<I',val) if reg==0xbc else [val]);time.sleep(0.015)
    started=time.monotonic()
    records=list(struct.iter_unpack('<II',blob))
    if '--paged' in sys.argv[3:]:
        for index in range(0,len(records),33):
            group=records[index:index+33]
            assert len(group)==33 and group[0][0]==0xf0
            assert [x[0] for x in group[1:]]==list(range(0,128,4))
            ts.write(0xf0,[group[0][1]])
            ts.write(0,b''.join(struct.pack('<I',v) for _,v in group[1:]))
    else:
        for off,val in records:
            assert off==0xf0 or (0<=off<=0x7c and off%4==0)
            ts.write(off,struct.pack('<I',val))
    print('FIRMWARE_UPLOAD_SECONDS',round(time.monotonic()-started,3),flush=True)
    # Prove data reached SRAM before starting the controller CPU.
    page=0;sample=None
    for off,val in records:
        if off==0xf0:page=val
        elif val:sample=(page,off,val)
    page,off,val=sample
    ts.write(0xf0,[page]);ts.read(off,4)
    actual=ts.read(off,4)
    print('SRAM_SAMPLE',hex(page),hex(off),actual.hex(),'EXPECTED',struct.pack('<I',val).hex(),flush=True)
    ts.write(0xe0,[0]);time.sleep(0.1)
    statuses=[]
    for i in range(5):
        status=ts.read(0xb0,4);statuses.append(status)
        print('STATUS',status.hex(),'HEARTBEAT',ts.read(0xb4,4).hex(),'TOUCH',ts.read(0x80,8).hex(),flush=True)
        time.sleep(0.2)
    assert all(s==b'\x5a'*4 for s in statuses),'Firmware did not reach a stable running state'
    print('SILEAD_SRAM_FIRMWARE_RUNNING; actual touch calibration still unverified',flush=True)
finally:
    if probe is not None:
        try:probe.stdin.write(b'q');probe.stdin.flush()
        except BrokenPipeError:pass
        probe.wait(timeout=5)
    if pmic:
        pmic.write(0x91,b'\xd5')
        print('RESTORED_CLDO2_ENABLE_MASK',pmic.read(0x91,1).hex(),flush=True)
