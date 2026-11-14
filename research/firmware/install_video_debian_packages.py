"""Import verified official Debian packages into apt's cache, then use apt."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

assert os.geteuid()==0
manifest=json.loads(Path('/home/debian/video-stage/debian-packages.json').read_text())
expected={r['file']:r for r in manifest}
with tarfile.open('/home/debian/video-stage/debian-packages.tar') as tf:
    assert {m.name for m in tf.getmembers()}==set(expected)
    for member in tf.getmembers():
        assert member.isfile() and Path(member.name).name==member.name and member.name.endswith('.deb')
        data=tf.extractfile(member).read();r=expected[member.name]
        assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'] and hashlib.md5(data).hexdigest()==r['apt_md5']
        (Path('/var/cache/apt/archives')/member.name).write_bytes(data)
env=dict(os.environ,DEBIAN_FRONTEND='noninteractive',LC_ALL='C.UTF-8')
subprocess.run(['apt-get','-y','--no-install-recommends','install','ffmpeg',
    'gstreamer1.0-tools','gstreamer1.0-plugins-base','gstreamer1.0-plugins-good','gstreamer1.0-plugins-bad',
    'gstreamer1.0-libav','gstreamer1.0-x','gstreamer1.0-gl'],check=True,env=env)
print('OFFICIAL_DEBIAN_MULTIMEDIA_DEPENDENCIES_INSTALLED',flush=True)
