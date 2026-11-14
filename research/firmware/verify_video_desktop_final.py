"""Confirm real desktop playback and capture the visible picture."""
import json,os,subprocess,time
from pathlib import Path
root=Path('/home/debian/video-stage/1080p')
common=['runuser','-u','debian','--','env','DISPLAY=:0','XAUTHORITY=/home/debian/.Xauthority','XDG_RUNTIME_DIR=/run/user/1000']
records=[]
for codec,name,seconds in (('h264','display-h264-10s.mp4',15),('hevc','display-hevc-5s.mp4',9)):
    with (root/f'player-final-{codec}.log').open('w') as stream:
        p=subprocess.Popen([*common,f'TZX_PLAYER_VERIFY_SECONDS={seconds}','/usr/local/bin/tzx-video-player',str(root/name)],stdout=stream,stderr=subprocess.STDOUT)
        time.sleep(3)
        if codec=='h264':
            subprocess.run([*common,'python3','/home/debian/capture_x11.py'],check=True,timeout=20)
            (root/'hardware-player-desktop.png').write_bytes(Path('/home/debian/desktop-capture.png').read_bytes())
        assert p.wait(timeout=seconds+20)==0
    record=json.loads(Path('/home/debian/video-player-result.json').read_text())
    assert record['eos'] and not record['errors']
    assert record['hardware_decoders']==['omxh264dec' if codec=='h264' else 'omxhevcvideodec']
    assert record['visible_dimensions']==[1920,1080] and record['display_frame_count']>50
    assert 'width=(int)960' in record['sink_input_caps'] and 'height=(int)540' in record['sink_input_caps']
    record['codec']=codec;record['file']=name
    (root/f'player-final-{codec}.json').write_text(json.dumps(record,indent=2)+'\n')
    records.append(record)
result=dict(status='PASS',records=records,scope='hardware decoder and actual X11 playback, scaled 960x540 with QoS; full 1080p60 presentation not qualified')
Path('/var/lib/tzx/video-desktop-qualified.json').write_text(json.dumps(result,indent=2)+'\n')
print('ACTUAL_H264_HEVC_DESKTOP_PLAYBACK_AND_VISIBLE_REGION_PASS',json.dumps(result),flush=True)
