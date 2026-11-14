#!/usr/bin/env python3
"""Render and verify desktop OpenGL 3.1 / GLSL 1.40 through headless EGL. MIT."""
import ctypes as C
import json
import os
from pathlib import Path
import time


def main():
    for name in ('LIBGL_ALWAYS_SOFTWARE', 'MESA_GL_VERSION_OVERRIDE', 'MESA_LOADER_DRIVER_OVERRIDE'):
        if os.environ.get(name):
            raise RuntimeError('Remove renderer/version override: ' + name)
    egl, gbm, gl = C.CDLL('libEGL.so.1'), C.CDLL('libgbm.so.1'), C.CDLL('libGL.so.1')
    P, I, U, F = C.c_void_p, C.c_int, C.c_uint, C.c_float

    def bind(lib, name, result, *arguments):
        f = getattr(lib, name); f.restype, f.argtypes = result, list(arguments)
        return f

    create_gbm = bind(gbm, 'gbm_create_device', P, I)
    destroy_gbm = bind(gbm, 'gbm_device_destroy', None, P)
    display_new = bind(egl, 'eglGetPlatformDisplay', P, U, P, P)
    initialize = bind(egl, 'eglInitialize', U, P, C.POINTER(I), C.POINTER(I))
    bind_api = bind(egl, 'eglBindAPI', U, U)
    choose = bind(egl, 'eglChooseConfig', U, P, C.POINTER(I), C.POINTER(P), I, C.POINTER(I))
    context_new = bind(egl, 'eglCreateContext', P, P, P, P, C.POINTER(I))
    current = bind(egl, 'eglMakeCurrent', U, P, P, P, P)
    context_destroy = bind(egl, 'eglDestroyContext', U, P, P)
    terminate = bind(egl, 'eglTerminate', U, P)
    string = bind(gl, 'glGetString', C.c_char_p, U)
    integer = bind(gl, 'glGetIntegerv', None, U, C.POINTER(I))
    shader_new = bind(gl, 'glCreateShader', U, U)
    shader_source = bind(gl, 'glShaderSource', None, U, I, C.POINTER(C.c_char_p), P)
    shader_compile = bind(gl, 'glCompileShader', None, U)
    shader_status = bind(gl, 'glGetShaderiv', None, U, U, C.POINTER(I))
    shader_log = bind(gl, 'glGetShaderInfoLog', None, U, I, P, P)
    program_new = bind(gl, 'glCreateProgram', U)
    attach = bind(gl, 'glAttachShader', None, U, U)
    link = bind(gl, 'glLinkProgram', None, U)
    program_status = bind(gl, 'glGetProgramiv', None, U, U, C.POINTER(I))
    use = bind(gl, 'glUseProgram', None, U)
    attribute = bind(gl, 'glGetAttribLocation', I, U, C.c_char_p)
    enable = bind(gl, 'glEnableVertexAttribArray', None, U)
    attr_pointer = bind(gl, 'glVertexAttribPointer', None, U, I, U, U, I, P)
    gen_buffers = bind(gl, 'glGenBuffers', None, I, C.POINTER(U))
    buffer_bind = bind(gl, 'glBindBuffer', None, U, U)
    buffer_data = bind(gl, 'glBufferData', None, U, C.c_ssize_t, P, U)
    gen_vaos = bind(gl, 'glGenVertexArrays', None, I, C.POINTER(U))
    vao_bind = bind(gl, 'glBindVertexArray', None, U)
    gen_textures = bind(gl, 'glGenTextures', None, I, C.POINTER(U))
    texture_bind = bind(gl, 'glBindTexture', None, U, U)
    texture_image = bind(gl, 'glTexImage2D', None, U, I, I, I, I, I, U, U, P)
    gen_fbos = bind(gl, 'glGenFramebuffers', None, I, C.POINTER(U))
    fbo_bind = bind(gl, 'glBindFramebuffer', None, U, U)
    fbo_texture = bind(gl, 'glFramebufferTexture2D', None, U, U, U, U, I)
    fbo_status = bind(gl, 'glCheckFramebufferStatus', U, U)
    viewport = bind(gl, 'glViewport', None, I, I, I, I)
    uniform_location = bind(gl, 'glGetUniformLocation', I, U, C.c_char_p)
    uniform = bind(gl, 'glUniform4f', None, I, F, F, F, F)
    draw = bind(gl, 'glDrawArrays', None, U, I, I)
    pixels_read = bind(gl, 'glReadPixels', None, I, I, I, I, U, U, P)
    error = bind(gl, 'glGetError', U)
    fd = os.open('/dev/dri/by-path/platform-tzx-de-scanout-card', os.O_RDWR | os.O_CLOEXEC)
    device, display, context = None, None, None
    started = time.monotonic()
    try:
        device = create_gbm(fd)
        if not device:
            raise RuntimeError('GBM device failed')
        display = display_new(0x31D7, device, None)
        major, minor = I(), I()
        if not initialize(display, C.byref(major), C.byref(minor)) or not bind_api(0x30A2):
            raise RuntimeError('EGL desktop OpenGL initialization failed')
        config, count = P(), I()
        if not choose(display, (I * 7)(0x3033, 0, 0x3040, 8, 0x3024, 8, 0x3038),
                      C.byref(config), 1, C.byref(count)) or not count.value:
            raise RuntimeError('No desktop OpenGL EGL configuration')
        context = context_new(display, config, None, (I * 5)(0x3098, 3, 0x30FB, 1, 0x3038))
        if not context or not current(display, None, None, context):
            raise RuntimeError('OpenGL 3.1 context failed')
        renderer, version, glsl = (string(code).decode() for code in (0x1F01, 0x1F02, 0x8B8C))
        gl_major, gl_minor = I(), I()
        integer(0x821B, C.byref(gl_major)); integer(0x821C, C.byref(gl_minor))
        if 'Mali-G57 (Panfrost)' not in renderer or (gl_major.value, gl_minor.value) < (3, 1):
            raise RuntimeError('Native OpenGL 3.1 unavailable: ' + renderer + '; ' + version)
        program = program_new()
        shaders = ((0x8B31, b'#version 140\nin vec2 p;void main(){gl_Position=vec4(p,0.0,1.0);}'),
                   (0x8B30, b'#version 140\nuniform vec4 c;out vec4 o;void main(){o=c;}'))
        for kind, source in shaders:
            shader = shader_new(kind)
            shader_source(shader, 1, (C.c_char_p * 1)(source), None); shader_compile(shader)
            status = I(); shader_status(shader, 0x8B81, C.byref(status))
            if not status.value:
                log = C.create_string_buffer(4096); shader_log(shader, len(log), None, log)
                raise RuntimeError('GLSL 1.40 compile failed: ' + log.value.decode())
            attach(program, shader)
        link(program); status = I(); program_status(program, 0x8B82, C.byref(status))
        if not status.value:
            raise RuntimeError('GLSL program link failed')
        use(program)
        vao, vbo = U(), U(); gen_vaos(1, C.byref(vao)); vao_bind(vao)
        gen_buffers(1, C.byref(vbo)); buffer_bind(0x8892, vbo)
        vertices = (F * 6)(-1, -1, 3, -1, -1, 3)
        buffer_data(0x8892, C.sizeof(vertices), vertices, 0x88E4)
        location = attribute(program, b'p'); enable(location); attr_pointer(location, 2, 0x1406, 0, 0, None)
        texture, fbo = U(), U(); gen_textures(1, C.byref(texture)); texture_bind(0x0DE1, texture)
        texture_image(0x0DE1, 0, 0x8058, 127, 65, 0, 0x1908, 0x1401, None)
        gen_fbos(1, C.byref(fbo)); fbo_bind(0x8D40, fbo)
        fbo_texture(0x8D40, 0x8CE0, 0x0DE1, texture, 0)
        if fbo_status(0x8D40) != 0x8CD5:
            raise RuntimeError('RGBA8 framebuffer incomplete')
        viewport(0, 0, 127, 65)
        location = uniform_location(program, b'c')
        pixels = (C.c_ubyte * (127 * 65 * 4))()
        for frame in range(64):
            color = [(frame * 37) & 255, (frame * 19) & 255, (frame * 73) & 255, 255]
            uniform(location, *(x / 255 for x in color)); draw(4, 0, 3)
            pixels_read(0, 0, 127, 65, 0x1908, 0x1401, pixels)
            got = bytes(pixels)
            if error() or any(abs(value - color[j % 4]) > 1 for j, value in enumerate(got)):
                raise RuntimeError('Desktop OpenGL framebuffer readback mismatch at frame ' + str(frame))
        print(json.dumps(dict(status='PASS', renderer=renderer, version=version, glsl=glsl,
            egl_version=f'{major.value}.{minor.value}', requested_api='desktop OpenGL 3.1',
            frames_checked=64, pixels_checked=64 * 127 * 65, full_frame_readback=True,
            elapsed_s=round(time.monotonic()-started, 3), cpu_fallback=False,
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())), flush=True)
    finally:
        if context:
            current(display, None, None, None); context_destroy(display, context)
        if display:
            terminate(display)
        if device:
            destroy_gbm(device)
        os.close(fd)


if __name__ == '__main__':
    main()
