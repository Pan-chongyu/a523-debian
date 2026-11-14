"""Report one-second microphone levels without saving or exposing speech."""
import array
import json
import math
import os
from pathlib import Path
import subprocess

assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
child=subprocess.Popen(['arecord','-q','-D','hw:0,0','-t','raw','-f','S16_LE','-r','48000',
                        '-c','1','-d','45','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
    for second in range(45):
        data=child.stdout.read(96000)
        if not data:break
        samples=array.array('h',data);mean=sum(samples)/len(samples)
        print(json.dumps({'second':second,'samples':len(samples),'dc':round(mean,2),
                          'rms':round(math.sqrt(sum((s-mean)**2 for s in samples)/len(samples)),2),
                          'minimum':min(samples),'maximum':max(samples)}),flush=True)
    _,errors=child.communicate(timeout=5)
    print('MICROPHONE_LEVEL_TEST_FINISHED',child.returncode,errors.decode(errors='replace'),flush=True)
finally:
    if child.poll() is None:child.kill();child.communicate()
