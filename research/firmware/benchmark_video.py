"""Measure steady decoding with both CPU-copy and DMA-buffer output."""
import json, os, subprocess, threading, time
from pathlib import Path
root=Path('/home/debian/video-stage/1080p')
env=dict(os.environ,**json.loads(Path('/opt/tzx-video/env.json').read_text()))
def irq():
    row=next(s for s in Path('/proc/interrupts').read_text().splitlines() if s.rstrip().endswith('cedar_dev'))
    return sum(map(int,row.split(':',1)[1].split()[:8]))
records=[]
for extension,parser,decoder in [('h264','h264parse','omxh264dec'),('hevc','h265parse','omxhevcvideodec')]:
    stream=root/('benchmark.'+extension)
    stream.write_bytes((root/('test.'+extension)).read_bytes()*5)
    for copy in (True,False):
        before=irq();start=time.monotonic();samples=[]
        p=subprocess.Popen(['gst-launch-1.0','-q','filesrc','location='+str(stream),'!',parser,'!',decoder,
            'disable-dma-feature='+str(copy).lower(),'!','fakesink','sync=false'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        while p.poll() is None and time.monotonic()-start<100:
            samples.append({'time':round(time.monotonic()-start,2),'irqs':irq()-before,
                've_mhz':int(Path('/sys/kernel/debug/clk/ve/clk_rate').read_text())//1000000,
                'cpu_khz':[int(p.read_text()) for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_cur_freq')],
                'cpu_max_khz':[int(p.read_text()) for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_max_freq')],
                'max_temp':max(int(p.read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'))})
            time.sleep(.4)
        if p.poll() is None:p.kill()
        stdout,stderr=p.communicate(timeout=10)
        elapsed=time.monotonic()-start;delta=irq()-before
        assert p.returncode==0,(p.returncode,stderr[-2000:])
        record={'codec':extension,'cpu_copy':copy,'frames':delta,'seconds':round(elapsed,3),'fps':round(delta/elapsed,2),'samples':samples}
        records.append(record)
        (root/'benchmark-result.json').write_text(json.dumps(records,indent=2)+'\n')
        print(json.dumps(record),flush=True)
    stream.unlink()
