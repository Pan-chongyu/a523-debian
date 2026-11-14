"""Board DMA32 heap and process-scoped Cedar allocation path trial."""
import ctypes,fcntl,hashlib,json,mmap,os,shutil,struct,subprocess
from pathlib import Path
assert os.geteuid()==0
source=Path('/home/debian/tzx_video_heap.ko')
assert hashlib.sha256(source.read_bytes()).hexdigest()=='e3c61454016f826d2f7920494313047527ac0ecd67401b6036005d7dde209f5e'
if not Path('/sys/module/tzx_video_heap').exists():subprocess.run(['insmod',str(source)],check=True)
device=Path('/dev/dma_heap/tzxvid');os.chmod(device,0o660)
subprocess.run(['chgrp','video',str(device)],check=True)
fd=os.open(device,os.O_RDONLY|os.O_CLOEXEC)
request=bytearray(struct.pack('<QIIQ',32*1024**2,0,os.O_RDWR|os.O_CLOEXEC,0))
fcntl.ioctl(fd,0xc0184800,request,True);os.close(fd)
_,buffer_fd,_,_=struct.unpack('<QIIQ',request)
buffer=mmap.mmap(buffer_fd,32*1024**2,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE)
address=ctypes.addressof(ctypes.c_char.from_buffer(buffer))
for offset in range(0,len(buffer),4096):buffer[offset]=offset//4096%251
for offset in range(0,len(buffer),4096):assert buffer[offset]==offset//4096%251
info=Path(f'/proc/self/fdinfo/{buffer_fd}').read_text()
assert 'tzxvid' in info
buffer.close();os.close(buffer_fd)
library=Path('/opt/tzx-video/usr/lib/aarch64-linux-gnu/libcdc_base.so')
backup=library.with_name('libcdc_base.system-heap-original')
if not backup.exists():shutil.copyfile(library,backup)
original=backup.read_bytes()
assert original.count(b'/dev/dma_heap/system')==1
patched=original.replace(b'/dev/dma_heap/system',b'/dev/dma_heap/tzxvid')
assert len(patched)==len(original) and library.read_bytes() in (original,patched)
library.write_bytes(patched)
proof=dict(status='PASS',module_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    allocated_pages=8192,mapped_pattern_check='PASS',physical_constraint='GFP_DMA32; PFNMAP addresses not exposed by pagemap',
    library=str(library),original_sha256=hashlib.sha256(original).hexdigest(),patched_sha256=hashlib.sha256(patched).hexdigest(),
    change='single equal-length /dev/dma_heap/system to /dev/dma_heap/tzxvid replacement')
Path('/home/debian/video-stage/dma32-heap-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print('BOARD_VIDEO_DMA32_HEAP_AND_SCOPED_LIBRARY_READY',json.dumps(proof),flush=True)
