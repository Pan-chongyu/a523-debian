import ctypes as c,os,subprocess,time,json
os.environ['DISPLAY']=':0'
os.environ['XAUTHORITY']='/home/debian/.Xauthority'
os.environ['XDG_RUNTIME_DIR']='/run/user/1000'
x=c.CDLL('libX11.so.6');t=c.CDLL('libXtst.so.6')
x.XOpenDisplay.argtypes=[c.c_char_p];x.XOpenDisplay.restype=c.c_void_p
x.XKeysymToKeycode.argtypes=[c.c_void_p,c.c_ulong];x.XKeysymToKeycode.restype=c.c_uint
x.XFlush.argtypes=[c.c_void_p];x.XCloseDisplay.argtypes=[c.c_void_p]
t.XTestFakeKeyEvent.argtypes=[c.c_void_p,c.c_uint,c.c_int,c.c_ulong]
d=x.XOpenDisplay(None);assert d
get=lambda:subprocess.check_output(['pactl','get-sink-volume','@DEFAULT_SINK@'],text=True)
rows=[{'event':'baseline','volume':get()}]
for name,symbol in [('up',0x1008ff13),('down',0x1008ff11)]:
    code=x.XKeysymToKeycode(d,symbol);assert code
    assert t.XTestFakeKeyEvent(d,code,1,0)
    assert t.XTestFakeKeyEvent(d,code,0,0)
    x.XFlush(d);time.sleep(2)
    rows.append({'event':name,'volume':get()})
x.XCloseDisplay(d)
print(json.dumps(rows,ensure_ascii=False,indent=2))
assert rows[1]['volume']!=rows[0]['volume']
assert rows[2]['volume']==rows[0]['volume']
print('DESKTOP_VOLUME_SHORTCUTS_PASS')
