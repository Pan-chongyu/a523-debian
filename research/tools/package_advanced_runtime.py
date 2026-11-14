import hashlib,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'build/advanced-files.tar.gz'
with tarfile.open(out,'w:gz') as tf:
    for name in ('tzx-video-runtime.py','tzx-video-player','tzx-video.service','install_video_runtime.py'):
        tf.add(root/'firmware'/name,arcname='video-stage/'+name)
    for name in ('sunxi-ve.ko','tzx_video_nodes.ko'):
        tf.add(root/'build/video'/name,arcname='video-stage/'+name)
    for name in ('linux-bundle.bin','linux-bundle.json','kernel.config','tzx_emmc_hs_lease.ko'):
        tf.add(root/'build/hs-kernel'/name,arcname='hs-kernel/'+name)
    tf.add(root/'firmware/install_hs_kernel.py',arcname='install_hs_kernel.py')
print(out.name,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
