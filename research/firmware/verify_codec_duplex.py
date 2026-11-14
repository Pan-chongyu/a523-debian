"""Test simultaneous PCM with silence, and report the clocks while it runs."""
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/proc/sys/kernel/panic_on_oops').read_text().strip() == '1'
subprocess.run(['amixer','-q','-c','0','cset','name=ADDA Loop Mode','0'], check=True)
subprocess.run(['amixer','-q','-c','0','cset','name=Master Playback Switch','0,0'], check=True)
capture = subprocess.Popen(['arecord','-q','-D','hw:0,0','-t','raw','-f','S16_LE','-r','48000',
                            '-c','1','-d','4','/dev/null'],stderr=subprocess.PIPE)
playback = None
result = {}
try:
    time.sleep(0.5)
    playback = subprocess.Popen(['aplay','-q','-D','hw:0,0','-t','raw','-f','S16_LE','-r','48000',
                                 '-c','2','-d','2','/dev/zero'],stderr=subprocess.PIPE)
    time.sleep(0.5)
    result['clocks'] = [line.strip() for line in Path('/sys/kernel/debug/clk/clk_summary').read_text().splitlines()
                        if 'audio-' in line or 'pll-audio' in line]
    result['capture_status'] = Path('/proc/asound/card0/pcm0c/sub0/status').read_text()
    result['playback_status'] = Path('/proc/asound/card0/pcm0p/sub0/status').read_text()
    _, errors = playback.communicate(timeout=6)
    result.update(playback_returncode=playback.returncode,playback_stderr=errors.decode(errors='replace'))
    _, errors = capture.communicate(timeout=6)
    result.update(capture_returncode=capture.returncode,capture_stderr=errors.decode(errors='replace'))
finally:
    for process in (playback,capture):
        if process is not None and process.poll() is None:
            process.kill();process.communicate()
result['kernel_tainted'] = int(Path('/proc/sys/kernel/tainted').read_text())
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['playback_returncode']==result['capture_returncode']==0 else 1)
