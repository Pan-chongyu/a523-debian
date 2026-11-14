"""Append the user's image sighting without altering frozen boot qualification."""
import hashlib,json,os,time
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx')
installed=json.loads((state/'boot-logo-installed.json').read_text())
proof=json.loads((state/'boot-logo-qualified.json').read_text())
pin='fc208e752fc816e1e016944cd0f4c4d9497989ec174718e5f3b12d030136b0ca'
assert installed['toc0_sha256']==proof['toc0_sha256']==pin
assert proof['status']=='PASS'
record=dict(toc0_sha256=pin,source_png_sha256=proof['actual_source_png_sha256'],
    observed_boot_id='a63e9bf9-2621-4808-a060-c5aac47892ce',
    question='修复后的第二次重启已完成。你是否看到了这张星空猫开屏图，且没有再出现彩条？图片方向、最终桌面和触摸是否正常？',
    user_reply='看到了',confirmed=dict(custom_image_seen=True),
    not_separately_confirmed=['absence_of_colorbars','image_orientation','desktop','touch','physical_key_boot_timing'],
    recorded_unix=int(time.time()),original_qualification_preserved=True)
path=state/'boot-logo-user-confirmation.json'
assert not path.exists()
temp=path.with_name(path.name+'.new')
data=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode()
with temp.open('wb') as stream:
    stream.write(data);os.fchmod(stream.fileno(),0o600);stream.flush();os.fsync(stream.fileno())
temp.replace(path)
descriptor=os.open(path.parent,os.O_DIRECTORY)
try:os.fsync(descriptor)
finally:os.close(descriptor)
assert path.read_bytes()==data
print('BOOT_LOGO_USER_IMAGE_SIGHTING_RECORDED',json.dumps(record,ensure_ascii=False),flush=True)
