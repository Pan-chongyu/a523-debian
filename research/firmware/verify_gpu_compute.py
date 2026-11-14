"""Run OpenGL ES 3.1 compute on the real Mali, checking every result word."""
import array
import ctypes as c
import json
import os
from pathlib import Path
import time

egl=c.CDLL('libEGL.so.1');gbm=c.CDLL('libgbm.so.1');gl=c.CDLL('libGLESv2.so.2')
ptr,i,u=c.c_void_p,c.c_int,c.c_uint


def bind(lib,name,result,args):
    f=getattr(lib,name);f.restype=result;f.argtypes=args;return f


create_gbm=bind(gbm,'gbm_create_device',ptr,[i])
destroy_gbm=bind(gbm,'gbm_device_destroy',None,[ptr])
get_display=bind(egl,'eglGetPlatformDisplay',ptr,[u,ptr,ptr])
initialize=bind(egl,'eglInitialize',u,[ptr,c.POINTER(i),c.POINTER(i)])
bind_api=bind(egl,'eglBindAPI',u,[u])
choose=bind(egl,'eglChooseConfig',u,[ptr,c.POINTER(i),c.POINTER(ptr),i,c.POINTER(i)])
context_new=bind(egl,'eglCreateContext',ptr,[ptr,ptr,ptr,c.POINTER(i)])
make_current=bind(egl,'eglMakeCurrent',u,[ptr,ptr,ptr,ptr])
destroy_context=bind(egl,'eglDestroyContext',u,[ptr,ptr])
terminate=bind(egl,'eglTerminate',u,[ptr])
get_string=bind(gl,'glGetString',c.c_char_p,[u])
get_error=bind(gl,'glGetError',u,[])
shader_new=bind(gl,'glCreateShader',u,[u])
shader_source=bind(gl,'glShaderSource',None,[u,i,c.POINTER(c.c_char_p),ptr])
compile_shader=bind(gl,'glCompileShader',None,[u])
shader_status=bind(gl,'glGetShaderiv',None,[u,u,c.POINTER(i)])
shader_log=bind(gl,'glGetShaderInfoLog',None,[u,i,ptr,c.c_char_p])
program_new=bind(gl,'glCreateProgram',u,[])
attach_shader=bind(gl,'glAttachShader',None,[u,u])
link=bind(gl,'glLinkProgram',None,[u])
program_status=bind(gl,'glGetProgramiv',None,[u,u,c.POINTER(i)])
use=bind(gl,'glUseProgram',None,[u])
uniform_location=bind(gl,'glGetUniformLocation',i,[u,c.c_char_p])
uniform=bind(gl,'glUniform1ui',None,[i,u])
gen_buffers=bind(gl,'glGenBuffers',None,[i,c.POINTER(u)])
bind_buffer=bind(gl,'glBindBuffer',None,[u,u])
buffer_data=bind(gl,'glBufferData',None,[u,c.c_ssize_t,ptr,u])
bind_base=bind(gl,'glBindBufferBase',None,[u,u,u])
dispatch=bind(gl,'glDispatchCompute',None,[u,u,u])
barrier=bind(gl,'glMemoryBarrier',None,[u])
fence=bind(gl,'glFenceSync',ptr,[u,u])
wait=bind(gl,'glClientWaitSync',u,[ptr,u,c.c_uint64])
delete_sync=bind(gl,'glDeleteSync',None,[ptr])
map_buffer=bind(gl,'glMapBufferRange',ptr,[u,c.c_ssize_t,c.c_ssize_t,u])
unmap=bind(gl,'glUnmapBuffer',u,[u])
fd=os.open('/dev/dri/by-path/platform-tzx-de-scanout-card',os.O_RDWR|os.O_CLOEXEC)
device=create_gbm(fd);assert device
display=get_display(0x31d7,device,None);context=None
try:
    major,minor=i(),i();assert initialize(display,c.byref(major),c.byref(minor))
    assert bind_api(0x30a0)
    attributes=(i*7)(0x3033,0,0x3040,0x40,0x3024,8,0x3038)
    config,count=ptr(),i();assert choose(display,attributes,c.byref(config),1,c.byref(count)) and count.value
    context=context_new(display,config,None,(i*5)(0x3098,3,0x30fb,1,0x3038));assert context
    assert make_current(display,None,None,context)
    renderer=get_string(0x1f01).decode();version=get_string(0x1f02).decode()
    assert 'Mali-G57' in renderer and 'OpenGL ES 3.1' in version,(renderer,version)
    source=b'''#version 310 es
precision highp int;
layout(local_size_x=64) in;
layout(std430,binding=0) buffer Values { uint v[]; };
uniform uint salt;
void main(){uint n=gl_GlobalInvocationID.x;v[n]=(v[n]^salt)*1664525u+1013904223u;}
'''
    shader=shader_new(0x91b9);sources=(c.c_char_p*1)(source)
    shader_source(shader,1,sources,None);compile_shader(shader)
    status=i();shader_status(shader,0x8b81,c.byref(status))
    log=c.create_string_buffer(4096);shader_log(shader,len(log),None,log)
    assert status.value,log.value
    program=program_new();attach_shader(program,shader);link(program)
    program_status(program,0x8b82,c.byref(status));assert status.value
    use(program);location=uniform_location(program,b'salt');assert location>=0
    words=65536;rounds=32
    expected=array.array('I',((n*2654435761)&0xffffffff for n in range(words)))
    initial=(c.c_uint*words).from_buffer_copy(expected)
    buffer=u();gen_buffers(1,c.byref(buffer));bind_buffer(0x90d2,buffer)
    buffer_data(0x90d2,len(expected)*4,initial,0x88e8);bind_base(0x90d2,0,buffer)
    tick=time.monotonic()
    for iteration in range(rounds):
        salt=(0xa5230000+iteration*7919)&0xffffffff;uniform(location,salt)
        dispatch(words//64,1,1);barrier(0x2200)
        expected=array.array('I',((((value^salt)*1664525)+1013904223)&0xffffffff for value in expected))
    sync=fence(0x9117,0);assert sync
    assert wait(sync,1,1000000000) in (0x911a,0x911c)
    delete_sync(sync)
    address=map_buffer(0x90d2,0,words*4,1);assert address
    observed=c.string_at(address,words*4)
    assert unmap(0x90d2)
    assert observed==expected.tobytes(),'SSBO compute readback mismatch'
    assert get_error()==0
    result=dict(status='PASS',renderer=renderer,version=version,shader='OpenGL ES 3.1 compute',
        words_checked=words,dispatches=rounds,integer_operations_checked=words*rounds,
        fence_and_SSBO_readback=True,elapsed_s=round(time.monotonic()-tick,3),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    print('MALI_G57_COMPUTE_ALL_WORDS_PASS',json.dumps(result),flush=True)
finally:
    if context:
        make_current(display,None,None,None);destroy_context(display,context)
    terminate(display);destroy_gbm(device);os.close(fd)
