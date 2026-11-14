"""Render actual kernel log records on the live boot buffer, then VT1."""
import collections,errno,json,mmap,os,select,socket,struct,subprocess,time
from pathlib import Path
root=Path('/usr/local/lib/tzx-boot-console')
font=(root/'font8x16.bin').read_bytes();assert len(font)==4096
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
rows=collections.deque(maxlen=43);count=0;frames=0;native=False
Path('/proc/sys/kernel/printk').write_text('4 4 1 7\n')
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x2d000) as log:
    assert struct.unpack_from('<I',log,0x600)[0]==0xa523b001
    assert struct.unpack_from('<I',log,0x60c)[0]==1
os.close(fd)
mem=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
fb=mmap.mmap(mem,4096000,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x42400000)
worker=subprocess.Popen([str(root/'render-log'),str(root/'font8x16.bin')],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
records=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK)
poll=select.poll();poll.register(records,select.POLLIN)
def pixels(text):
    color=0xffe0e6ed
    if 'fail' in text.lower() or 'error' in text.lower():color=0xffffb870
    return [[color if font[(ord(ch) if 32<=ord(ch)<127 else 63)*16+y] & (128>>x) else 0xff09111c
             for ch in text[:148].ljust(148) for x in range(8)] for y in range(16)]
def render():
    global frames,native
    if Path('/sys/module/tzx_display').exists():native=True;return
    # The native 800x1280 DMA buffer is a right-rotated 1280x800 canvas.
    lines=['TZX A523  |  Debian Linux  |  LIVE BOOT LOG',
           'Kernel messages below are read directly from /dev/kmsg.',
           '-'*148]+list(rows)
    data=('\n'.join(lines)+'\n').encode('ascii',errors='replace')
    worker.stdin.write(struct.pack('<I',len(data))+data);worker.stdin.flush()
    assert worker.stdout.read(1)==b'1';frames+=1
    if frames==1 and 'NOTIFY_SOCKET' in os.environ:
        address=os.environ['NOTIFY_SOCKET'];address='\0'+address[1:] if address.startswith('@') else address
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as notify:
            notify.connect(address);notify.sendall(b'READY=1\nSTATUS=Live kernel log visible on the retained boot display')
try:
    last=0;last_count=-1;until=time.monotonic()+85
    while time.monotonic()<until:
        if Path('/sys/module/tzx_display').exists() and not native:
            native=True
            # Native fbcon gets the same authentic history; never write the
            # old physical buffer after its display owner changes.
            try:
                Path('/sys/class/graphics/fbcon/rotate').write_text('1')
                tty=os.open('/dev/tty1',os.O_WRONLY|os.O_NOCTTY)
                os.write(tty,('\x1b[2J\x1b[H'+ '\r\n'.join(rows)+'\r\n').encode());os.close(tty)
            except OSError:pass
        changed=False
        for _ in range(150):
            try:data=os.read(records,16384).decode(errors='replace')
            except BlockingIOError:break
            except OSError as e:
                if e.errno==errno.EPIPE:continue
                raise
            header,_,body=data.partition(';');parts=header.split(',')
            if len(parts)<3 or not body.strip():continue
            seconds=int(parts[2])/1e6;message=f'[{seconds:8.3f}] '+body.splitlines()[0]
            # Keep actual service/kernel information; avoid a video of
            # repeated Wi-Fi packet dumps which hides useful startup state.
            if len(message)>148:message=message[:145]+'...'
            rows.append(message);count+=1;changed=True
            if native:
                try:
                    tty=os.open('/dev/tty1',os.O_WRONLY|os.O_NOCTTY)
                    os.write(tty,(message+'\r\n').encode());os.close(tty)
                except OSError:pass
        now=time.monotonic()
        if not native and count!=last_count and now-last>.25:
            render();last=now;last_count=count
        if native and Path('/run/tzx-boot-streamline-desktop.json').exists():
            obj=json.loads(Path('/run/tzx-boot-streamline-desktop.json').read_text())
            if obj.get('boot_id')==boot and obj.get('status')=='PASS':break
        poll.poll(100)
finally:
    result=dict(boot_id=boot,records=count,physical_frames=frames,native_takeover=native,
                completed_kernel_s=time.monotonic(),source='/dev/kmsg',result='PASS' if frames and native else 'INCOMPLETE')
    Path('/var/lib/tzx/boot-console-log.json').write_text(json.dumps(result,indent=2)+'\n')
    worker.stdin.close();worker.wait(timeout=3)
    fb.close();os.close(mem);os.close(records)
    print('BOOT_CONSOLE_REAL_LOG_RESULT',json.dumps(result),flush=True)
