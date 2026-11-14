"""Play quiet, separated test beeps for at most two minutes, then mute again."""
import array
import argparse
import math
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=90, choices=range(5,121))
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/module/tzx_codec_driver').is_dir()
assert int(Path('/proc/sys/kernel/tainted').read_text()) & 128 == 0


def control(name,value):
    subprocess.run(['amixer','-q','-c','0','cset','name='+name,value],check=True)


pcm = array.array('h')
for i in range(48000):
    value = int(4096*math.sin(2*math.pi*700*i/48000)) if i<16800 else 0
    # 5 ms fade avoids abrupt starts/stops.
    if i<240: value=int(value*i/240)
    elif 16560<=i<16800: value=int(value*(16800-i)/240)
    pcm.extend((value,value))
try:
    control('ADDA Loop Mode','0')
    control('Master Playback Volume','127,127')
    control('Lineout Playback Volume','31')
    control('Master Playback Switch','1,1')
    print('QUIET_TONE_RUNNING',args.seconds,flush=True)
    with tempfile.TemporaryFile() as source:
        source.write(pcm.tobytes()*args.seconds);source.seek(0)
        subprocess.run(['aplay','-q','-D','hw:0,0','-t','raw','-f','S16_LE','-r','48000','-c','2'],
                       stdin=source,check=True,timeout=args.seconds+10)
finally:
    control('Master Playback Switch','0,0')
    control('Lineout Playback Volume','0')
print('QUIET_TONE_FINISHED_MUTED',flush=True)
