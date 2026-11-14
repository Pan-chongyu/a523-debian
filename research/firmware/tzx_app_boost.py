"""Short application/input boosts through existing cpufreq minimum requests.

The CPU driver's lease, speed bin and native thermal maximum retain authority.
systemd's independent watchdog and ExecStopPost restore 120 MHz after failure.
"""
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import stat
import struct
import sys
import time

ROOT=Path('/usr/local/lib/tzx-app-launch')
POLICIES=[Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0,4)]
SOCKET=Path('/run/tzx-app-boost.sock')
BEFORE=Path('/run/tzx-app-boost-before.json')
STATUS=Path('/run/tzx-app-boost.json')
BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
BASE=[120000,120000]
MAXIMUM=[1416000,1800000]
EVENT=struct.Struct('llHHi')
assert sys.argv[1:] in (['run'],['restore']) and os.geteuid()==0

def atomic(path,value):
    temporary=path.with_suffix('.new')
    with temporary.open('w') as stream:
        os.fchmod(stream.fileno(),0o600)
        json.dump(value,stream,indent=2);stream.write('\n')
    temporary.replace(path)

def restore():
    if BEFORE.exists():
        before=json.loads(BEFORE.read_text())
        assert before['boot_id']==BOOT and before['minimum_khz']==BASE
        for policy,value in zip(POLICIES,BASE):
            if policy.exists():(policy/'scaling_min_freq').write_text(str(value))
    atomic(STATUS,{'boot_id':BOOT,'state':'stopped','minimum_khz':BASE})

if sys.argv[1]=='restore':
    restore();raise SystemExit(0)

assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
manifest=json.loads((ROOT/'manifest.json').read_text())
for name,digest in manifest['files'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
# The owner uses Type=exec: its start job can finish before module replacement
# and its first lease/status have completed. Wait for the owner's real readiness.
for attempt in range(100):
    try:
        owner=json.loads(Path('/run/tzx-cpu-dvfs.json').read_text())
        ready=owner['boot_id']==BOOT and owner['state']=='active' and all(
            (p/'scaling_driver').read_text().strip()=='tzx-a523-dvfs2' for p in POLICIES)
        if ready:break
    except (OSError,KeyError,json.JSONDecodeError):pass
    time.sleep(.2)
else:raise RuntimeError('CPU owner did not finish initializing')
assert [int((p/'scaling_min_freq').read_text()) for p in POLICIES]==BASE
assert Path('/sys/module/tzx_cpu_dvfs_cooling_v2/parameters/first_trip').read_text().strip()=='70000'
assert Path('/sys/module/tzx_cpu_dvfs_cooling_v2/parameters/second_trip').read_text().strip()=='80000'
atomic(BEFORE,{'boot_id':BOOT,'minimum_khz':BASE})
stopping=False
def stop(*_):
    global stopping
    stopping=True
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)

def notify(value):
    address=os.environ.get('NOTIFY_SOCKET')
    if not address:return
    if address.startswith('@'):address='\0'+address[1:]
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
        channel.connect(address);channel.sendall(value.encode())

selector=selectors.DefaultSelector()
inputs=[]
listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
deadline=0;requests=0;input_presses=0;last_notify=0;last_state=None
try:
    if SOCKET.exists():
        info=SOCKET.lstat();assert stat.S_ISSOCK(info.st_mode) and info.st_uid==0
        SOCKET.unlink()
    listener.bind(str(SOCKET));os.chown(SOCKET,0,1000);SOCKET.chmod(0o660)
    listener.listen(4);listener.setblocking(False);selector.register(listener,selectors.EVENT_READ,'request')
    for entry in Path('/sys/class/input').glob('event*'):
        name=(entry/'device/name').read_text().strip()
        if name not in ('TZX GSL3670 candidate','TZX P30 LRADC volume keys','TZX P30 AXP717 power key'):continue
        fd=os.open('/dev/input/'+entry.name,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
        inputs.append(fd);selector.register(fd,selectors.EVENT_READ,'input')
    assert len(inputs)==3
    notify('READY=1\nWATCHDOG=1\nSTATUS=Input and application boost ready')
    last_notify=time.monotonic()
    while not stopping:
        now=time.monotonic()
        active=now<deadline
        events=selector.select(.05 if active else .5)
        clients=[]
        for key,_ in events:
            if key.data=='request':
                client,_=listener.accept();client.settimeout(.03)
                try:
                    _,uid,_=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    if uid in (0,1000) and client.recv(16)==b'boost\n':
                        deadline=time.monotonic()+4.0;requests+=1;clients.append(client)
                    else:client.close()
                except OSError:client.close()
            else:
                try:data=os.read(key.fd,EVENT.size*128)
                except BlockingIOError:continue
                assert data and len(data)%EVENT.size==0
                for offset in range(0,len(data),EVENT.size):
                    _,_,kind,code,value=EVENT.unpack_from(data,offset)
                    # Presses only; idle SYN frames and tracking-id releases do not boost.
                    if (kind==1 and value==1) or (kind==3 and code==57 and value>=0):
                        deadline=time.monotonic()+4.0;input_presses+=1
        now=time.monotonic();active=now<deadline
        if not all((p/'scaling_driver').read_text().strip()=='tzx-a523-dvfs2' for p in POLICIES):
            raise RuntimeError('CPU owner changed; stop requesting boosts')
        assert Path('/sys/module/tzx_cpufreq_dvfs_v2/parameters/clock_fault').read_text().strip()=='0'
        ceilings=[int((p/'scaling_max_freq').read_text()) for p in POLICIES]
        desired=[min(cap,maximum) if active else base for cap,maximum,base in zip(ceilings,MAXIMUM,BASE)]
        for policy,wanted in zip(POLICIES,desired):
            if int((policy/'scaling_min_freq').read_text())!=wanted:
                (policy/'scaling_min_freq').write_text(str(wanted))
        for client in clients:
            try:client.sendall(b'OK\n')
            except OSError:pass
            client.close()
        state=(active,tuple(desired),requests,input_presses)
        if state!=last_state:
            atomic(STATUS,dict(boot_id=BOOT,state='boosting' if active else 'idle',minimum_khz=desired,
                maximum_unchanged_khz=ceilings,boost_seconds=4,launch_requests=requests,input_presses=input_presses,
                temperature_limits_unchanged=True,governor_unchanged=True))
            last_state=state
        if now-last_notify>=1:
            notify('WATCHDOG=1');last_notify=now
finally:
    for fd in inputs:os.close(fd)
    selector.close();listener.close()
    SOCKET.unlink(missing_ok=True)
    restore()
