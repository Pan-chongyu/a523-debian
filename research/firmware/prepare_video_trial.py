"""Stage vendor codec libraries in an isolated prefix and load guarded VPU nodes."""
import configparser
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1'
assert hashlib.sha256(gzip.decompress(Path('/proc/config.gz').read_bytes())).hexdigest()=='59cc725631e95f3726080322e19f4868ef461035e85d6f7dd02b5be2915aced6'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
stage=Path('/home/debian/video-stage');root=Path('/opt/tzx-video')
digests={'sunxi-ve.ko':'37a685c4657e234e1e79812757f9a2940fc5fa9782f95607a2780777cbecd799',
         'tzx_video_nodes.ko':'5fa3ee3281ddcf305ce9d54532e0f689122f20a3a1a04504eba97c973facfd97',
         'userspace.tar.gz':'34412a0d474e295895482bedc4bd6a13e9dce7137745a24b3b7085ab0fcd54a8'}
for name,digest in digests.items(): assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest,name
if not root.exists():
    root.mkdir()
    with tarfile.open(stage/'userspace.tar.gz') as tf: tf.extractall(root,filter='data')
else:
    assert (root/'env.json').exists() and not Path('/sys/module/tzx_video_nodes').exists()
config=configparser.ConfigParser(strict=False)
config.read(root/'etc/xdg/gstomx-allwinner.conf')
for section in list(config.sections()):
    if section not in ('omxh264dec','omxhevcvideodec'): config.remove_section(section)
    else:
        config[section]['core-name']=str(root/'usr/lib/aarch64-linux-gnu/libOmxCore.so')
        config[section]['rank']='0' # Explicit test pipelines only until verified.
with (root/'etc/xdg/gstomx-allwinner.conf').open('w') as f: config.write(f)
(root/'env.json').write_text(json.dumps({'LD_LIBRARY_PATH':str(root/'usr/lib/aarch64-linux-gnu'),
    'GST_PLUGIN_PATH':str(root/'usr/lib/aarch64-linux-gnu/gstreamer-1.0'),
    'GST_OMX_CONFIG_DIR':str(root/'etc/xdg'),'GST_REGISTRY':'/home/debian/video-stage/gst-registry.bin'},indent=2)+'\n')
subprocess.run(['modprobe','system_heap'],check=True)
assert Path('/dev/dma_heap/system').exists()
subprocess.run(['python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'],check=True,timeout=30)
subprocess.run(['insmod',str(stage/'tzx_video_nodes.ko')],check=True,timeout=20)
subprocess.run(['insmod',str(stage/'sunxi-ve.ko')],check=True,timeout=20)
assert Path('/dev/cedar_dev').exists()
print('VPU_PROVIDER_AND_DEVICE_CREATED_DECODE_NOT_YET_VERIFIED',flush=True)
print(subprocess.check_output(['dmesg'],text=True).splitlines()[-35:])
os.sync()
