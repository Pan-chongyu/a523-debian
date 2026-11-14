"""Report tone-band input levels without retaining or transmitting recordings."""
import array
import json
import math
from pathlib import Path
import subprocess

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
capture = subprocess.run(['arecord','-q','-D','hw:0,0','-t','raw','-f','S16_LE','-r','48000',
                          '-c','1','-d','4','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
samples = array.array('h',capture.stdout)
segments=[]
for start in range(0,len(samples)-4799,4800):
    segment=samples[start:start+4800];mean=sum(segment)/len(segment)
    values=[s-mean for s in segment]
    real=sum(v*math.cos(2*math.pi*700*i/48000) for i,v in enumerate(values))
    imag=sum(v*math.sin(2*math.pi*700*i/48000) for i,v in enumerate(values))
    segments.append({'seconds':start/48000,'ac_rms':round(math.sqrt(sum(v*v for v in values)/len(values)),2),
                     'tone_700_amplitude':round(2*math.hypot(real,imag)/len(values),2)})
print(json.dumps({'samples':len(samples),'returncode':capture.returncode,'stderr':capture.stderr.decode(errors='replace'),
                  'segments':segments},indent=2))
