"""Inspect a disposable Firefox renderer and close it through Gecko, not SIGKILL."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('mode', choices=('default','noafbc','software'))
a=p.parse_args()
assert os.geteuid()==0
values=None
for proc in Path('/proc').glob('[0-9]*'):
    try:
        if proc.stat().st_uid==1000 and (proc/'comm').read_text().strip()=='xfce4-session':
            values=dict(s.split('=',1) for s in (proc/'environ').read_bytes().decode().split('\0') if '=' in s)
            break
    except OSError:pass
assert values and values['DISPLAY']==':0'
env={k:values[k] for k in ('DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR') if k in values}
env['MOZ_REMOTE_ALLOW_SYSTEM_ACCESS']='1'
if a.mode=='noafbc':env['PAN_MESA_DEBUG']='noafbc'
folder=Path('/home/debian/browser-graphics-profile');folder.mkdir(exist_ok=True);os.chown(folder,1000,1000)
profile=folder/a.mode;profile.mkdir(exist_ok=True);os.chown(profile,1000,1000)
preferences={'marionette.port':28283,'remote.prefs.recommended':False,
    'browser.shell.checkDefaultBrowser':False,'browser.startup.homepage_override.mstone':'ignore',
    'browser.startup.page':0,'browser.newtabpage.enabled':False,
    'datareporting.policy.dataSubmissionEnabled':False,'toolkit.telemetry.enabled':False,
    'network.captive-portal-service.enabled':False,'browser.region.network.url':'',
    'network.connectivity-service.enabled':False,'browser.startup.homepage':'about:blank'}
if a.mode=='software':preferences['gfx.webrender.software']=True
(profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+','+json.dumps(v)+');\n' for k,v in preferences.items()))
os.chown(profile/'user.js',1000,1000)
prefix=['runuser','-u','debian','--','env',*(k+'='+v for k,v in env.items())]
before=subprocess.check_output(['dmesg'],text=True).splitlines()
record={'mode':a.mode,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
log=(folder/(a.mode+'.log')).open('w')
child=subprocess.Popen([*prefix,'firefox-esr','--no-remote','--marionette','--profile',str(profile),'about:blank'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
sock=None;number=0;started=time.monotonic()
def receive():
    header=b''
    while not header.endswith(b':'):
        value=sock.recv(1)
        assert value,'browser connection closed'
        header+=value
    size=int(header[:-1]);assert size<4000000
    body=b''
    while len(body)<size:
        value=sock.recv(size-len(body));assert value
        body+=value
    return json.loads(body)
def command(name,params):
    global number
    number+=1
    message=json.dumps([0,number,name,params]).encode()
    sock.sendall(str(len(message)).encode()+b':'+message)
    result=receive();assert result[0:2]==[1,number] and result[2] is None,result
    return result[3]
try:
    while time.monotonic()-started<90:
        try:
            sock=socket.create_connection(('127.0.0.1',28283),timeout=2)
            sock.settimeout(45);break
        except OSError:
            if child.poll() is not None:raise RuntimeError(('early browser exit',child.returncode))
            time.sleep(.2)
    assert sock,'Firefox automation startup timed out'
    record['handshake']=receive()
    command('WebDriver:NewSession',{'capabilities':{'alwaysMatch':{'pageLoadStrategy':'normal'}}})
    record['automation_ready_seconds']=round(time.monotonic()-started,3)
    command('Marionette:SetContext',{'value':'chrome'})
    value=command('WebDriver:ExecuteAsyncScript',{'script':'''const done=arguments[arguments.length-1];
      const {Troubleshoot}=ChromeUtils.importESModule("resource://gre/modules/Troubleshoot.sys.mjs");
      Troubleshoot.snapshot().then(s=>done({graphics:s.graphics,version:s.application.version}));''',
      'args':[],'newSandbox':True,'sandbox':'default','scriptTimeout':45000})
    record['troubleshoot']=value
    command('Marionette:SetContext',{'value':'content'})
    record['canvas']=command('WebDriver:ExecuteAsyncScript',{'script':'''const done=arguments[arguments.length-1];
      document.body.innerHTML='<canvas width="640" height="480"></canvas>';
      const canvas=document.querySelector('canvas');const c=canvas.getContext('2d');
      let frames=0;let start=performance.now();
      function draw(t){c.fillStyle='#17465f';c.fillRect(0,0,640,480);
        for(let i=0;i<80;i++){c.fillStyle=`hsl(${(i*9+frames)%360} 80% 55%)`;
          c.fillRect((i*83+frames*3)%640,(i*61)%480,34,34);}
        frames++;if(t-start<3000)requestAnimationFrame(draw);
        else done({frames,seconds:(t-start)/1000});}requestAnimationFrame(draw);''',
      'args':[],'newSandbox':True,'sandbox':'default','scriptTimeout':45000})
    command('Marionette:Quit',{'flags':['eAttemptQuit']})
    child.wait(timeout=25)
    record['clean_exit']=child.returncode
finally:
    if sock:sock.close()
    if child.poll() is None:
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:child.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    log.close()
    after=subprocess.check_output(['dmesg'],text=True).splitlines()
    record['new_kernel_messages']=after[len(before):] if after[:len(before)]==before else after
    (folder/(a.mode+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    print('BROWSER_GRAPHICS_PROFILE',json.dumps(record),flush=True)
