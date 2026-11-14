"""SRAM FEL bootstrap, based on the project's verified PyUSB transport."""
import hashlib,json,struct,time
from pathlib import Path

class Fel:
    def __init__(self,helper):
        self.helper=Path(helper).read_bytes();self.usb=None;self.capacity=0;self.cid=None
        if not 0<len(self.helper)<32768:raise ValueError('Invalid FEL helper')
    def send(self,data):
        for offset in range(0,len(data),131072):
            block=data[offset:offset+131072]
            if self.usb.write(self.out_ep,block,timeout=10000)!=len(block):raise IOError('Short FEL write')
    def receive(self,length):
        result=bytearray()
        while len(result)<length:
            block=self.usb.read(self.in_ep,min(length-len(result),131072),timeout=10000)
            if not len(block):raise IOError('Empty FEL read')
            result.extend(block)
        return bytes(result)
    def usb_request(self,operation,length):
        data=bytearray(32);data[:4]=b'AWUC';struct.pack_into('<IIHI',data,8,length,0x0c000000,operation,length);self.send(data)
    def ack(self):
        if struct.unpack('<4sIIB',self.receive(13))!=(b'AWUS',0,0,0):raise IOError('Bad FEL acknowledgement')
    def usb_write(self,data):self.usb_request(0x12,len(data));self.send(data);self.ack()
    def usb_read(self,length):self.usb_request(0x11,length);data=self.receive(length);self.ack();return data
    def request(self,op,address=0,length=0):self.usb_write(struct.pack('<4I',op,address,length,0))
    def status(self):
        value=self.usb_read(8)
        if value[:2]==b'\xff\xff' and value[4]:raise IOError('FEL operation rejected')
    def write_raw(self,address,data):self.request(0x101,address,len(data));self.usb_write(data);self.status()
    def read_raw(self,address,length):self.request(0x103,address,length);data=self.usb_read(length);self.status();return data
    def execute(self,address):self.request(0x102,address);self.status()
    def connect(self):
        import usb.util,libusb_package
        matches=list(libusb_package.find(find_all=True,idVendor=0x1f3a,idProduct=0xefe8))
        if len(matches)!=1:raise RuntimeError('Connect exactly one tablet in FEL mode (1f3a:efe8)')
        self.usb=matches[0];usb.util.claim_interface(self.usb,0)
        endpoints=[ep for ep in self.usb.get_active_configuration()[(0,0)] if usb.util.endpoint_type(ep.bmAttributes)==2]
        self.in_ep=next(ep.bEndpointAddress for ep in endpoints if ep.bEndpointAddress&0x80)
        self.out_ep=next(ep.bEndpointAddress for ep in endpoints if not ep.bEndpointAddress&0x80)
        self.request(1);version=self.usb_read(32);self.status()
        if version[:8]!=b'AWUSBFEX' or struct.unpack_from('<I',version,8)[0]!=0x00189000:raise ValueError('Wrong FEL SoC')
        self.write_raw(0x20000,self.helper)
        if self.read_raw(0x20000,len(self.helper))!=self.helper:raise IOError('FEL helper readback mismatch')
    def operation(self,op,lba=0,count=0):
        if op!=3 and (not self.cid or not 0<count<=128 or lba<0 or lba+count>self.capacity):raise ValueError('Unverified target/range')
        if op not in (1,2,3):raise ValueError('Unsupported helper operation')
        self.write_raw(0x2fff0,struct.pack('<4I',op,lba,count,0));self.write_raw(0x07090100,struct.pack('<I',1));self.execute(0x20000)
        for _ in range(160):
            status=struct.unpack('<I',self.read_raw(0x07090100,4))[0]
            if status==0xaa:return
            if status==0xee:raise IOError('eMMC helper failed '+self.read_raw(0x07090100,16).hex())
            time.sleep(.05)
        raise TimeoutError('eMMC helper timeout')
    def identify(self):
        self.operation(3);data=self.read_raw(0x30000,528)
        cid=data[:16][::-1].hex();capacity=struct.unpack_from('<I',data,16+212)[0]
        if not cid.startswith('3e01ff55454d2020') or capacity!=244318208 or data[16+179]&7:
            raise ValueError('eMMC model/capacity/partition does not match this board profile')
        self.cid=cid;self.capacity=capacity;return dict(cid=cid,sectors=capacity)
    def read(self,lba,count):self.operation(1,lba,count);return self.read_raw(0x30000,count*512)
    def write_verified(self,lba,data):
        if not data or len(data)%512 or len(data)>65536:raise ValueError('Bad FEL block')
        self.write_raw(0x30000,data)
        if self.read_raw(0x30000,len(data))!=data:raise IOError('FEL staging mismatch')
        self.operation(2,lba,len(data)//512)
        if self.read(lba,len(data)//512)!=data:raise IOError('eMMC bootstrap readback mismatch')
    def bootstrap(self,bundle,toc,header,nonce,progress=lambda done,total:None):
        if not self.cid:raise RuntimeError('Call identify before bootstrap')
        for offset in range(0,len(bundle),65536):
            self.write_verified(98304+offset//512,bundle[offset:offset+65536]);progress(offset+len(bundle[offset:offset+65536]),len(bundle))
        self.write_verified(128,nonce+bytes(512-len(nonce)))
        self.write_verified(4096,header);self.write_verified(256,toc)
    def reboot(self):
        self.write_raw(0x07090110,bytes(16))
        self.write_raw(0x0205000c,struct.pack('<I',0x14af))
        self.write_raw(0x02050010,struct.pack('<I',0x16aa0001))
        self.write_raw(0x02050014,struct.pack('<I',0x16aa0011))
    def close(self):
        if self.usb is not None:
            import usb.util
            usb.util.dispose_resources(self.usb);self.usb=None
