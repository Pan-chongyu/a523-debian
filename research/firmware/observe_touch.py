"""Capture touch events and raw axis bounds during a physical gesture test."""
import fcntl, glob, json, os, select, struct, sys, time
from pathlib import Path
paths=[]
for event in glob.glob('/sys/class/input/event*'):
    name=Path(event,'device/name').read_text().strip()
    if 'TZX GSL3670' in name:paths.append('/dev/input/'+Path(event).name)
assert len(paths)==1,paths
fd=os.open(paths[0],os.O_RDONLY|os.O_NONBLOCK)
start=time.monotonic();end=start+float(sys.argv[1] if len(sys.argv)>1 else 90)
report=Path(sys.argv[2]) if len(sys.argv)>2 else None
stop=Path('/run/tzx-touch-capture-stop')
stop.unlink(missing_ok=True)
samples=[];ranges={53:[],54:[]};keys=[];counter=0
events=[];slots={};slot=0;max_contacts=0;frames=0
declared={}
for axis in (53,54):
    info=fcntl.ioctl(fd,0x80184540+axis,bytes(24))
    value,minimum,maximum,fuzz,flat,resolution=struct.unpack('6i',info)
    declared[axis]=[minimum,maximum]
def save():
    if report:
        payload={'elapsed':round(time.monotonic()-start,3),'device':paths[0],
                 'declared_axes':declared,'absolute_events':counter,'frames':frames,
                 'max_contacts':max_contacts,'events':events,
                 'axis_ranges':{axis:[min(values),max(values)] if values else None for axis,values in ranges.items()}}
        temporary=report.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload))
        temporary.replace(report)
next_report=start+5
print('TOUCH_CAPTURE_READY',paths[0],declared,flush=True)
save()
while time.monotonic()<end and not stop.exists():
    if time.monotonic()>=next_report:
        print('TOUCH_PROGRESS',round(time.monotonic()-start,1),'ABS',counter,
              'AXES',{axis:(len(values),min(values),max(values)) if values else None
                      for axis,values in ranges.items()},flush=True)
        next_report=time.monotonic()+5
        save()
    if not select.select([fd],[],[],0.5)[0]:continue
    for sec,usec,kind,code,value in struct.iter_unpack('llHHi',os.read(fd,24*1024)):
        elapsed=round(time.monotonic()-start,4)
        events.append((elapsed,kind,code,value))
        if kind==3:
            counter+=1
            if code==47:slot=value
            if code==57:
                if value<0:slots.pop(slot,None)
                else:slots[slot]=value
            if code in ranges:ranges[code].append(value)
            if len(samples)<50:samples.append((round(time.monotonic()-start,2),code,value))
        if kind==1:keys.append((code,value))
        if kind==0 and code==0:
            frames+=1;max_contacts=max(max_contacts,len(slots))
save()
print('ABS_EVENTS',counter,'SAMPLES',samples,flush=True)
for axis,values in ranges.items():print('AXIS',axis,'COUNT',len(values),'RANGE',(min(values),max(values)) if values else None,flush=True)
print('TOUCH_CAPTURE_END',flush=True)
print('FRAMES',frames,'MAX_CONTACTS',max_contacts,flush=True)
