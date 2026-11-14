"""Read only named codec controls during a short ADC test; retain no recording."""
import array
import json
import mmap
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-periph1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert Path('/sys/module/tzx_codec_driver').is_dir()
addresses = (0x00, 0x04, 0x10, 0x30, 0x34, 0x50, 0x300, 0x310, 0x318, 0x348)
result = {}
with open('/dev/mem', 'rb', buffering=0) as source:
    with mmap.mmap(source.fileno(), 4096, flags=mmap.MAP_SHARED,
                   prot=mmap.PROT_READ, offset=0x07110000) as registers:
        def snapshot():
            return {f'{offset:03x}': f'{int.from_bytes(registers[offset:offset+4], "little"):08x}'
                    for offset in addresses}
        result['idle'] = snapshot()
        child = subprocess.Popen(['arecord', '-D', 'hw:0,0', '-t', 'raw', '-f', 'S16_LE',
                                  '-r', '48000', '-c', '1', '-d', '3', '-'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(0.7)
            result['running'] = snapshot()
            directory = Path('/sys/kernel/debug/asoc/TZX A523/analog:7110000.audio-codec/dapm')
            result['dapm'] = {name: (directory / name).read_text()
                              for name in ('ADC1', 'Mic Bias', 'MIC1', 'Capture')}
            output, errors = child.communicate(timeout=6)
        except BaseException:
            child.kill()
            child.communicate()
            raise
        samples = array.array('h', output)
        result.update(returncode=child.returncode, stderr=errors.decode(errors='replace'),
                      samples=len(samples), unique_values=len(set(samples)),
                      minimum=min(samples) if samples else None,
                      maximum=max(samples) if samples else None)
        result['after'] = snapshot()
print(json.dumps(result, indent=2))
