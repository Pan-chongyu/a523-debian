# SPDX-License-Identifier: GPL-2.0-only
"""Render a triangle through the render node and verify real GPU pixels."""
import ctypes as c
import json
import os
import time
import argparse

gbm = c.CDLL('libgbm.so.1')
egl = c.CDLL('libEGL.so.1')
gl = c.CDLL('libGLESv2.so.2')


def bind(lib, name, restype, argtypes):
    function = getattr(lib, name)
    function.restype = restype
    function.argtypes = argtypes
    return function


ptr, integer, uint = c.c_void_p, c.c_int, c.c_uint
create_gbm = bind(gbm, 'gbm_create_device', ptr, [integer])
destroy_gbm = bind(gbm, 'gbm_device_destroy', None, [ptr])
get_display = bind(egl, 'eglGetPlatformDisplay', ptr, [uint, ptr, ptr])
initialize = bind(egl, 'eglInitialize', uint, [ptr, c.POINTER(integer), c.POINTER(integer)])
bind_api = bind(egl, 'eglBindAPI', uint, [uint])
choose = bind(egl, 'eglChooseConfig', uint, [ptr, c.POINTER(integer), c.POINTER(ptr), integer, c.POINTER(integer)])
create_context = bind(egl, 'eglCreateContext', ptr, [ptr, ptr, ptr, c.POINTER(integer)])
make_current = bind(egl, 'eglMakeCurrent', uint, [ptr, ptr, ptr, ptr])
destroy_context = bind(egl, 'eglDestroyContext', uint, [ptr, ptr])
terminate = bind(egl, 'eglTerminate', uint, [ptr])
get_string = bind(gl, 'glGetString', c.c_char_p, [uint])
get_error = bind(gl, 'glGetError', uint, [])
gen_textures = bind(gl, 'glGenTextures', None, [integer, c.POINTER(uint)])
bind_texture = bind(gl, 'glBindTexture', None, [uint, uint])
texture_image = bind(gl, 'glTexImage2D', None, [uint, integer, integer, integer, integer, integer, uint, uint, ptr])
gen_fbos = bind(gl, 'glGenFramebuffers', None, [integer, c.POINTER(uint)])
bind_fbo = bind(gl, 'glBindFramebuffer', None, [uint, uint])
attach_texture = bind(gl, 'glFramebufferTexture2D', None, [uint, uint, uint, uint, integer])
check_fbo = bind(gl, 'glCheckFramebufferStatus', uint, [uint])
create_shader = bind(gl, 'glCreateShader', uint, [uint])
shader_source = bind(gl, 'glShaderSource', None, [uint, integer, c.POINTER(c.c_char_p), ptr])
compile_shader = bind(gl, 'glCompileShader', None, [uint])
shader_status = bind(gl, 'glGetShaderiv', None, [uint, uint, c.POINTER(integer)])
shader_log = bind(gl, 'glGetShaderInfoLog', None, [uint, integer, ptr, c.c_char_p])
create_program = bind(gl, 'glCreateProgram', uint, [])
attach_shader = bind(gl, 'glAttachShader', None, [uint, uint])
link_program = bind(gl, 'glLinkProgram', None, [uint])
program_status = bind(gl, 'glGetProgramiv', None, [uint, uint, c.POINTER(integer)])
use_program = bind(gl, 'glUseProgram', None, [uint])
get_attribute = bind(gl, 'glGetAttribLocation', integer, [uint, c.c_char_p])
enable_attribute = bind(gl, 'glEnableVertexAttribArray', None, [uint])
attribute_pointer = bind(gl, 'glVertexAttribPointer', None, [uint, integer, uint, uint, integer, ptr])
viewport = bind(gl, 'glViewport', None, [integer, integer, integer, integer])
clear_color = bind(gl, 'glClearColor', None, [c.c_float]*4)
clear = bind(gl, 'glClear', None, [uint])
draw = bind(gl, 'glDrawArrays', None, [uint, integer, integer])
read_pixels = bind(gl, 'glReadPixels', None, [integer, integer, integer, integer, uint, uint, ptr])
finish = bind(gl, 'glFinish', None, [])


def shader(kind, source):
    handle = create_shader(kind)
    sources = (c.c_char_p*1)(source)
    shader_source(handle, 1, sources, None)
    compile_shader(handle)
    status = integer()
    shader_status(handle, 0x8B81, c.byref(status))
    log = c.create_string_buffer(4096)
    shader_log(handle, len(log), None, log)
    assert status.value, log.value
    return handle


parser = argparse.ArgumentParser()
parser.add_argument('--node', default='/dev/dri/renderD128')
args = parser.parse_args()
fd = os.open(args.node, os.O_RDWR | os.O_CLOEXEC)
device = create_gbm(fd)
assert device
display = get_display(0x31D7, device, None)  # EGL_PLATFORM_GBM_KHR
context = None
try:
    major, minor = integer(), integer()
    assert initialize(display, c.byref(major), c.byref(minor))
    assert bind_api(0x30A0)  # EGL_OPENGL_ES_API
    attributes = (integer*11)(0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3033, 0, 0x3040, 4, 0x3038)
    config, count = ptr(), integer()
    assert choose(display, attributes, c.byref(config), 1, c.byref(count)) and count.value
    context = create_context(display, config, None, (integer*3)(0x3098, 2, 0x3038))
    assert context and make_current(display, None, None, context)
    renderer = get_string(0x1F01).decode()
    version = get_string(0x1F02).decode()
    assert 'Mali-G57' in renderer and 'llvmpipe' not in renderer.lower(), renderer
    texture, framebuffer = uint(), uint()
    gen_textures(1, c.byref(texture))
    bind_texture(0x0DE1, texture)
    texture_image(0x0DE1, 0, 0x1908, 64, 64, 0, 0x1908, 0x1401, None)
    gen_fbos(1, c.byref(framebuffer))
    bind_fbo(0x8D40, framebuffer)
    attach_texture(0x8D40, 0x8CE0, 0x0DE1, texture, 0)
    assert check_fbo(0x8D40) == 0x8CD5
    program = create_program()
    attach_shader(program, shader(0x8B31, b'attribute vec2 position; void main(){gl_Position=vec4(position,0.0,1.0);}'))
    attach_shader(program, shader(0x8B30, b'precision mediump float; void main(){gl_FragColor=vec4(1.0,0.0,0.0,1.0);}'))
    link_program(program)
    status = integer()
    program_status(program, 0x8B82, c.byref(status))
    assert status.value
    use_program(program)
    location = get_attribute(program, b'position')
    assert location >= 0
    vertices = (c.c_float*6)(-1, -1, 1, -1, 0, 1)
    enable_attribute(location)
    attribute_pointer(location, 2, 0x1406, 0, 0, vertices)
    viewport(0, 0, 64, 64)
    clear_color(0, 0, 1, 1)
    started = time.monotonic()
    clear(0x4000)
    draw(4, 0, 3)
    finish()
    pixels = (c.c_ubyte*(64*64*4))()
    read_pixels(0, 0, 64, 64, 0x1908, 0x1401, pixels)
    assert get_error() == 0
    def pixel(x, y): return list(pixels[(y*64+x)*4:(y*64+x+1)*4])
    inside, outside = pixel(32, 24), pixel(0, 63)
    assert inside == [255, 0, 0, 255] and outside == [0, 0, 255, 255], (inside, outside)
    print(json.dumps({'renderer': renderer, 'gl_version': version,
        'egl_version': f'{major.value}.{minor.value}', 'inside_rgba': inside,
        'outside_rgba': outside, 'elapsed_s': round(time.monotonic()-started, 4),
        'result': 'GPU_SHADER_AND_PIXEL_READBACK_PASS'}), flush=True)
finally:
    if context:
        make_current(display, None, None, None)
        destroy_context(display, context)
    terminate(display)
    destroy_gbm(device)
    os.close(fd)
