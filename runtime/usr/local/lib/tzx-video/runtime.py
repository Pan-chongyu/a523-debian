#!/usr/bin/env python3
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
root=Path('/usr/local/lib/tzx-video')
mods={'tzx_video_nodes.ko':'5fa3ee3281ddcf305ce9d54532e0f689122f20a3a1a04504eba97c973facfd97','sunxi-ve.ko':'37a685c4657e234e1e79812757f9a2940fc5fa9782f95607a2780777cbecd799'}
assert os.geteuid()==0 and os.uname().release=='7.3.3-tzx-a523-accel1'
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()==Path('/etc/tzx/device-cid').read_text().strip()
assert Path('/sys/firmware/devicetree/base/soc/iommu@2010000/phandle').read_bytes()==bytes.fromhex('00000090')
if len(sys.argv)!=2 or sys.argv[1] not in ('start','stop'):raise SystemExit(2)
if sys.argv[1]=='start':
    subprocess.run(['modprobe','system_heap'],check=True)
    for name,digest in mods.items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
        if not Path('/sys/module/'+name[:-3].replace('-','_')).exists():
            subprocess.run(['insmod',str(root/name)],check=True,timeout=20)
    for attempt in range(100):
        if Path('/dev/cedar_dev').exists() and Path('/dev/dma_heap/system').exists():break
        time.sleep(.1)
    else:raise RuntimeError('VPU provider did not finish probing')
    for device in ('/dev/cedar_dev','/dev/dma_heap/system'):
        os.chmod(device,0o660);subprocess.run(['chgrp','video',device],check=True)
    Path('/run/tzx-video-ready.json').write_text(json.dumps({'status':'ready','release':os.uname().release,'modules':mods})+'\n')
else:
    for name in ('sunxi-ve','tzx_video_nodes'):
        if Path('/sys/module/'+name.replace('-','_')).exists():
            subprocess.run(['rmmod',name],check=True,timeout=30)
