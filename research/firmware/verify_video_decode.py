"""Compare real VPU output with software decoding, including IRQ activity."""
import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import sys

root=Path('/home/debian/video-stage');boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
large='--1080p' in sys.argv
width,height,frames,rate=(1920,1080,120,60) if large else (640,368,60,30)
if large:root=root/'1080p';root.mkdir(exist_ok=True)
env=dict(os.environ,**json.loads(Path('/opt/tzx-video/env.json').read_text()),LC_ALL='C.UTF-8')
env['GST_REGISTRY']=str(root/'gst-registry-named.bin')
assert Path('/dev/cedar_dev').exists()
def run(*args,timeout=90):
    r=subprocess.run(args,capture_output=True,text=True,env=env,timeout=timeout)
    assert r.returncode==0,(args,r.returncode,r.stdout[-2000:],r.stderr[-2000:])
    return r
def irq(name):
    rows=[s for s in Path('/proc/interrupts').read_text().splitlines() if s.rstrip().endswith(name)]
    assert len(rows)==1,(name,rows)
    return sum(map(int,rows[0].split(':',1)[1].split()[:8]))
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()
assert irq('2010000.iommu')==0
records=[];watchdog=os.open('/dev/watchdog',os.O_WRONLY);stop=threading.Event()
seconds=array.array('i',[16]);fcntl.ioctl(watchdog,0xc0045706,seconds,True)
deadline=time.monotonic()+600
def ping():
    while not stop.wait(2):
        if time.monotonic()<deadline:os.write(watchdog,b'\0')
thread=threading.Thread(target=ping,daemon=True);thread.start()
try:
    for codec,encoder,parser,decoder,extension in (
        ('h264','libx264','h264parse','omxh264dec','h264'),
        ('hevc','libx265','h265parse','omxhevcvideodec','hevc')):
        stream=root/('test.'+extension);expected=root/(codec+'-software.yuv');actual=root/(codec+'-hardware.yuv')
        params=['-x264-params','keyint=30:scenecut=0'] if codec=='h264' else ['-x265-params','pools=2:frame-threads=2:log-level=error:keyint=30']
        run('ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i',f'testsrc2=size={width}x{height}:rate={rate}',
            '-frames:v',str(frames),'-an','-c:v',encoder,'-preset','fast','-threads','4','-bf','2',*params,str(stream),timeout=200)
        run('ffmpeg','-hide_banner','-loglevel','error','-y','-threads','4','-i',str(stream),'-pix_fmt','yuv420p','-f','rawvideo',str(expected))
        before=irq('cedar_dev');started=time.monotonic()
        result=run('gst-launch-1.0','-e','-q','filesrc','location='+str(stream),'!',parser,'!',decoder,
            'disable-dma-feature=true','!','videoconvert','!','video/x-raw,format=I420','!','filesink','location='+str(actual),timeout=70)
        (root/(codec+'-gst.log')).write_text(result.stdout+'\n'+result.stderr)
        after=irq('cedar_dev');assert after>before+30,(before,after)
        assert irq('2010000.iommu')==0
        expected_bytes=width*height*3//2*frames
        assert expected.stat().st_size==expected_bytes
        # OMX exports each plane with a 32-line slice height. filesink writes
        # those allocation padding rows too; compare only the visible pixels.
        slice_height=(height+31)&~31
        if actual.stat().st_size!=expected_bytes:
            frame_bytes=width*slice_height*3//2
            assert actual.stat().st_size==frame_bytes*frames,actual.stat().st_size
            visible=hashlib.sha256()
            with actual.open('rb') as f:
                for i in range(frames):
                    frame=f.read(frame_bytes);assert len(frame)==frame_bytes
                    visible.update(frame[:width*height])
                    for offset in (width*slice_height,width*slice_height*5//4):visible.update(frame[offset:offset+width*height//4])
            hardware_hash=visible.hexdigest()
        else:hardware_hash=sha(actual)
        assert hardware_hash==sha(expected),(codec,hardware_hash,sha(expected))
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
        record={'codec':codec,'width':width,'height':height,'frames':frames,'bytes':expected_bytes,'bit_exact_sha256':hardware_hash,
                'hardware_buffer_bytes':actual.stat().st_size,'plane_slice_height':slice_height,
                'hardware_irq_delta':after-before,'iommu_fault_irqs':irq('2010000.iommu'),'seconds':round(time.monotonic()-started,3)}
        before=irq('cedar_dev');started=time.monotonic()
        speed=run('gst-launch-1.0','-e','-q','filesrc','location='+str(stream),'!',parser,'!',decoder,
            'disable-dma-feature=true','!','fakesink','sync=false',timeout=70)
        decode_seconds=time.monotonic()-started;delta=irq('cedar_dev')-before
        assert delta>=frames
        record.update(memory_sink_seconds=round(decode_seconds,3),including_startup_fps=round(frames/decode_seconds,2),speed_run_irq_delta=delta)
        records.append(record);print('ACTUAL_HARDWARE_DECODE_PIXEL_EXACT_PASS',json.dumps(record),flush=True)
        (root/'decode-progress.json').write_text(json.dumps(records,indent=2)+'\n')
        if large:actual.unlink();expected.unlink()
    record={'status':'PASS','boot_id':boot,'records':records,'software_fallback_allowed':False}
    (root/'decode-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print('H264_H265_VPU_DECODE_BOTH_BIT_EXACT_PASS',flush=True)
finally:
    stop.set();thread.join(3);os.write(watchdog,b'V');os.close(watchdog)
