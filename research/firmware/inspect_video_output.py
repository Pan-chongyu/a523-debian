import hashlib,json
from pathlib import Path
root=Path('/home/debian/video-stage')
a=(root/'h264-hardware.yuv').read_bytes();b=(root/'h264-software.yuv').read_bytes()
w,h,frames=640,368,60;stride=w;sliceheight=384;size=stride*sliceheight*3//2
assert len(a)==size*frames
out=bytearray()
for i in range(frames):
    frame=a[i*size:(i+1)*size]
    out+=frame[:w*h]
    for offset in (w*sliceheight,w*sliceheight*5//4):out+=frame[offset:offset+w*h//4]
print('SLICE_HEIGHT_CROPPED_OUTPUT',json.dumps({'equal':out==b,'hw_sha256':hashlib.sha256(out).hexdigest(),
    'sw_sha256':hashlib.sha256(b).hexdigest(),'hw_Y_0_sha':hashlib.sha256(out[:w*h]).hexdigest(),
    'sw_Y_0_sha':hashlib.sha256(b[:w*h]).hexdigest()}))
print((root/'h264-gst.log').read_text()[-6000:])
