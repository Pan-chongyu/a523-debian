#!/usr/bin/env python3
"""A523 player using the vendor codec prefix only in its own process."""
import ctypes,json,os,subprocess,sys
from pathlib import Path
for key,value in json.loads(Path('/opt/tzx-video/env.json').read_text()).items(): os.environ[key]=value
import gi
gi.require_version('Gst','1.0')
gi.require_version('Gtk','3.0')
gi.require_version('GdkX11','3.0')
gi.require_version('GstVideo','1.0')
from gi.repository import Gst,Gtk,Gdk,GdkX11,GstVideo
Gst.init(None)
if len(sys.argv)>1:
    path=Path(sys.argv[1]).expanduser().resolve()
else:
    dialog=Gtk.FileChooserDialog(title='打开视频',action=Gtk.FileChooserAction.OPEN)
    dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'打开',Gtk.ResponseType.OK)
    result=dialog.run();filename=dialog.get_filename();dialog.destroy()
    if result!=Gtk.ResponseType.OK:raise SystemExit(0)
    path=Path(filename).resolve()
if not path.is_file():raise SystemExit('文件不存在：'+str(path))
requested_scale=0
try:
    media=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(path)],timeout=10))['streams'][0]
    if os.environ.get('TZX_VIDEO_FULL_RES')!='1':
        while requested_scale<2 and (media['width']/(1<<requested_scale)>1280 or media['height']/(1<<requested_scale)>800):requested_scale+=1
except (OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError):pass
window=Gtk.Window(title='A523 硬件视频播放器')
window.set_default_size(1000,650)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.add(box)
use_gl=os.environ.get('TZX_VIDEO_USE_GL','1')=='1'
sink=Gst.ElementFactory.make('glimagesink' if use_gl else 'gtksink','video')
if sink is None:raise SystemExit('缺少 gstreamer1.0-gtk3')
sink.set_property('force-aspect-ratio',True)
if sink.find_property('qos'):sink.set_property('qos',True)
if sink.find_property('max-lateness'):sink.set_property('max-lateness',20000000)
play=Gst.ElementFactory.make('playbin','playbin')
crop=Gst.ElementFactory.make('videocrop','visible-crop')
scale_caps=Gst.ElementFactory.make('capsfilter','display-size')
convert=Gst.ElementFactory.make('videoconvert','display-convert')
output=Gst.Bin.new('output');output.add(crop)
if use_gl:
    scale_caps.set_property('caps',Gst.Caps.from_string('video/x-raw,format=I420'))
    output.add(scale_caps);output.add(sink)
    assert crop.link(scale_caps) and scale_caps.link(sink)
else:
    output.add(convert);output.add(sink)
    assert crop.link(convert) and convert.link(sink)
input_pad=crop.get_static_pad('sink')
output.add_pad(Gst.GhostPad.new('sink',input_pad))
play.set_property('uri',path.as_uri());play.set_property('video-sink',output)
decoders=[];errors=[];eos=False;visible=[0,0];frame_count=0;hardware_scale=0;eos_stats=None
def parser_caps(pad,_):
    caps=pad.get_current_caps()
    if caps:
        s=caps.get_structure(0)
        if s.has_field('width') and s.has_field('height'):
            visible[:]=[s.get_value('width'),s.get_value('height')]
def crop_caps(_pad,info):
    event=info.get_event()
    if event and event.type==Gst.EventType.CAPS:
        s=event.parse_caps().get_structure(0)
        width,height=s.get_value('width'),s.get_value('height')
        vw,vh=[(n+(1<<hardware_scale)-1)>>hardware_scale for n in visible]
        if vw and vh and 0<=width-vw<64 and 0<=height-vh<32:
            crop.set_property('right',width-vw);crop.set_property('bottom',height-vh)
    return Gst.PadProbeReturn.OK
input_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM,crop_caps)
def count_frame(_pad,_info):
    global frame_count
    frame_count+=1;return Gst.PadProbeReturn.OK
sink.get_static_pad('sink').add_probe(Gst.PadProbeType.BUFFER,count_frame)
def deep_added(bin,sub,element):
    global hardware_scale
    factory=element.get_factory()
    if factory and factory.get_name() in ('h264parse','h265parse'):
        element.get_static_pad('src').connect('notify::caps',parser_caps)
    if element.find_property('disable-dma-feature'):
        # Copy out of unrestricted VE pages before GPU upload, because this
        # board's Panfrost workaround requires physical addresses below 4GiB.
        element.set_property('disable-dma-feature',True)
        if element.find_property('scale'):
            hardware_scale=requested_scale;element.set_property('scale',hardware_scale)
        decoders.append(element.get_factory().get_name())
        print('HARDWARE_DECODER_SELECTED',decoders[-1],flush=True)
play.connect('deep-element-added',deep_added)
video_widget=Gtk.DrawingArea() if use_gl else sink.props.widget
box.pack_start(video_widget,True,True,0)
controls=Gtk.Box(spacing=8)
toggle=Gtk.Button(label='暂停');controls.pack_start(toggle,False,False,8)
seek=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1)
seek.set_draw_value(False);controls.pack_start(seek,True,True,0)
volume=Gtk.VolumeButton();volume.set_value(.5);play.set_property('volume',.5)
volume.connect('value-changed',lambda _,v:play.set_property('volume',v))
controls.pack_start(volume,False,False,0)
full=Gtk.Button(label='全屏');full.connect('clicked',lambda _:window.fullscreen())
controls.pack_start(full,False,False,4)
box.pack_end(controls,False,False,4)
status=Gtk.Label(label=path.name);box.pack_end(status,False,False,2)
def toggle_play(_):
    if play.get_state(0).state==Gst.State.PLAYING:
        play.set_state(Gst.State.PAUSED);toggle.set_label('播放')
    else:play.set_state(Gst.State.PLAYING);toggle.set_label('暂停')
toggle.connect('clicked',toggle_play)
changing=False
def seek_changed(_):
    if changing:return
    ok,duration=play.query_duration(Gst.Format.TIME)
    if ok:play.seek_simple(Gst.Format.TIME,Gst.SeekFlags.FLUSH|Gst.SeekFlags.KEY_UNIT,int(duration*seek.get_value()/100))
seek.connect('value-changed',seek_changed)
def tick():
    global changing
    ok,position=play.query_position(Gst.Format.TIME);valid,duration=play.query_duration(Gst.Format.TIME)
    if ok and valid and duration>0:
        changing=True;seek.set_value(position*100/duration);changing=False
        status.set_text(path.name+'   '+('硬件解码 · 流畅模式' if decoders and hardware_scale else '硬件解码' if decoders else '软件解码'))
    return True
def bus(_bus,msg):
    global eos,eos_stats
    if msg.type==Gst.MessageType.ERROR:
        err,detail=msg.parse_error();status.set_text('播放错误：'+err.message);print(err,detail,file=sys.stderr,flush=True)
        errors.append(err.message)
    elif msg.type==Gst.MessageType.EOS:
        final_sink=sink.get_property('sink') if use_gl else sink
        eos_stats=final_sink.get_property('stats').to_string()
        play.set_state(Gst.State.PAUSED);toggle.set_label('播放')
        eos=True
        print('PLAYBACK_EOS',flush=True)
play.get_bus().add_signal_watch();play.get_bus().connect('message',bus)
screen_connection=None
def close(*_):
    global screen_connection
    play.set_state(Gst.State.NULL);Gtk.main_quit()
    if screen_connection:
        x11.XCloseDisplay(screen_connection);screen_connection=None
window.connect('destroy',close)
window.connect('key-press-event',lambda _,e:window.unfullscreen() if e.keyval==Gdk.KEY_Escape else False)
from gi.repository import GLib
if os.environ.get('TZX_PLAYER_VERIFY_SECONDS'):
    def verify_finished():
        final_sink=sink.get_property('sink') if use_gl else sink
        sample=final_sink.get_property('last-sample')
        report={'hardware_decoders':decoders,'hardware_scale':hardware_scale,'errors':errors,'eos':eos,
                'visible_dimensions':visible,'display_frame_count':frame_count,
                'sink_input_caps':sink.get_static_pad('sink').get_current_caps().to_string() if sink.get_static_pad('sink').get_current_caps() else None,
                'last_frame_caps':sample.get_caps().to_string() if sample else None,
                'last_frame_bytes':sample.get_buffer().get_size() if sample else 0,
                'sink_stats':eos_stats or final_sink.get_property('stats').to_string()}
        Path('/home/debian/video-player-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PLAYER_VERIFIED',json.dumps(report),flush=True)
        close();return False
    GLib.timeout_add_seconds(int(os.environ['TZX_PLAYER_VERIFY_SECONDS']),verify_finished)
GLib.timeout_add(500,tick)
window.show_all()
if use_gl:GstVideo.VideoOverlay.set_window_handle(sink,video_widget.get_window().get_xid())
try:
    x11=ctypes.CDLL('libX11.so.6');xss=ctypes.CDLL('libXss.so.1');xext=ctypes.CDLL('libXext.so.6')
    x11.XOpenDisplay.argtypes=[ctypes.c_char_p];x11.XOpenDisplay.restype=ctypes.c_void_p
    x11.XCloseDisplay.argtypes=[ctypes.c_void_p];x11.XResetScreenSaver.argtypes=[ctypes.c_void_p];x11.XFlush.argtypes=[ctypes.c_void_p]
    xss.XScreenSaverSuspend.argtypes=[ctypes.c_void_p,ctypes.c_int]
    xext.DPMSForceLevel.argtypes=[ctypes.c_void_p,ctypes.c_ushort]
    screen_connection=x11.XOpenDisplay(None)
    if screen_connection:
        xss.XScreenSaverSuspend(screen_connection,1);x11.XResetScreenSaver(screen_connection)
        xext.DPMSForceLevel(screen_connection,0);x11.XFlush(screen_connection)
except OSError:pass
play.set_state(Gst.State.PLAYING);Gtk.main()
