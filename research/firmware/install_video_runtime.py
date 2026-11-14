"""Install only the qualified scoped VPU runtime and its desktop launcher."""
import configparser,hashlib,json,os,shutil,subprocess
from pathlib import Path
stage=Path('/home/debian/video-stage');out=Path('/usr/local/lib/tzx-video')
assert os.geteuid()==0
proof=json.loads((stage/'1080p/decode-result.json').read_text())
assert proof['status']=='PASS' and len(proof['records'])==2
assert all(r['frames']==120 and r['width']==1920 and r['iommu_fault_irqs']==0 for r in proof['records'])
out.mkdir(exist_ok=True)
for name in ('sunxi-ve.ko','tzx_video_nodes.ko','tzx-video-runtime.py','tzx-video-player'):
    dest=out/({'tzx-video-runtime.py':'runtime.py','tzx-video-player':'player.py'}.get(name,name))
    shutil.copyfile(stage/name,dest);dest.chmod(0o755 if name.endswith('.py') or name=='tzx-video-player' else 0o644)
config=configparser.ConfigParser(strict=False)
config.read('/opt/tzx-video/etc/xdg/gstomx-allwinner.conf')
assert set(config.sections())=={'omxh264dec','omxhevcvideodec'}
for section in config: 
    if section!='DEFAULT':config[section]['rank']='257'
with Path('/opt/tzx-video/etc/xdg/gstomx-allwinner.conf').open('w') as f:config.write(f)
env=json.loads(Path('/opt/tzx-video/env.json').read_text())
env['GST_REGISTRY']='/home/debian/.cache/tzx-video-registry.bin'
Path('/opt/tzx-video/env.json').write_text(json.dumps(env,indent=2)+'\n')
wrapper=Path('/usr/local/bin/tzx-video-player')
wrapper.write_text("#!/bin/sh\nexport LD_LIBRARY_PATH=/opt/tzx-video/usr/lib/aarch64-linux-gnu\nexport GST_PLUGIN_PATH=/opt/tzx-video/usr/lib/aarch64-linux-gnu/gstreamer-1.0\nexport GST_OMX_CONFIG_DIR=/opt/tzx-video/etc/xdg\nexport GST_REGISTRY=\"$HOME/.cache/tzx-video-registry.bin\"\nexec /usr/bin/python3 /usr/local/lib/tzx-video/player.py \"$@\"\n")
wrapper.write_text(wrapper.read_text().replace('exec /usr/bin/python3','export GST_GL_API=gles2\nexport GST_GL_PLATFORM=egl\nexec /usr/bin/python3'))
wrapper.chmod(0o755)
desktop=Path('/usr/share/applications/tzx-video-player.desktop')
desktop.write_text('[Desktop Entry]\nType=Application\nName=A523 硬件视频播放器\nComment=H.264 / H.265 视频硬件解码\nExec=/usr/local/bin/tzx-video-player %f\nIcon=video-x-generic\nTerminal=false\nCategories=AudioVideo;Player;\nMimeType=video/mp4;video/x-matroska;video/x-msvideo;video/mpeg;\n')
rules=Path('/etc/udev/rules.d/70-tzx-video.rules')
rules_text='KERNEL=="cedar_dev", GROUP="video", MODE="0660"\nSUBSYSTEM=="dma_heap", KERNEL=="system", GROUP="video", MODE="0660"\n'
assert not rules.exists() or rules.read_text()==rules_text
rules.write_text(rules_text)
cedar=Path('/etc/cedarc.conf')
vendor=Path('/opt/tzx-video/etc/cedarc.conf')
assert not cedar.exists() or cedar.read_bytes()==vendor.read_bytes()
if not cedar.exists():shutil.copyfile(vendor,cedar)
shutil.copyfile(stage/'tzx-video.service','/etc/systemd/system/tzx-video.service')
subprocess.run(['udevadm','control','--reload-rules'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','tzx-video.service'],check=True,timeout=40)
Path('/var/lib/tzx/video-qualified.json').write_text(json.dumps(proof,indent=2)+'\n')
files=[out/'runtime.py',out/'player.py',out/'sunxi-ve.ko',out/'tzx_video_nodes.ko',wrapper,desktop,rules,cedar,Path('/etc/systemd/system/tzx-video.service')]
receipt={'status':'installed','files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'qualification':proof}
Path('/var/lib/tzx/video-installed.json').write_text(json.dumps(receipt,indent=2)+'\n')
os.sync();print('QUALIFIED_VIDEO_AUTOSTART_AND_DESKTOP_PLAYER_INSTALLED',flush=True)
