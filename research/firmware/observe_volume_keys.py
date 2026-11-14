import json,os,select,struct,subprocess,time
from pathlib import Path
name='TZX P30 LRADC volume keys'
paths=[p for p in Path('/sys/class/input').glob('event*') if (p/'device/name').read_text().strip()==name]
assert len(paths)==1
fd=os.open('/dev/input/'+paths[0].name,os.O_RDONLY|os.O_NONBLOCK)
start=time.monotonic()
print('VOLUME_EVENT_OBSERVATION_READY',paths[0].name,flush=True)
try:
    while time.monotonic()-start<180:
        if not select.select([fd],[],[],.5)[0]:continue
        raw=os.read(fd,24*64)
        for at in range(0,len(raw),24):
            sec,usec,kind,code,value=struct.unpack('llHHi',raw[at:at+24])
            if kind==1:
                volume=subprocess.run(['runuser','-u','debian','--','env','XDG_RUNTIME_DIR=/run/user/1000','pactl','get-sink-volume','@DEFAULT_SINK@'],capture_output=True,text=True).stdout.strip()
                print(json.dumps({'second':round(time.monotonic()-start,3),'key':code,'value':value,'pulse_volume':volume},ensure_ascii=False),flush=True)
finally:os.close(fd)
