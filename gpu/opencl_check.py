#!/usr/bin/env python3
"""Check real Mali-G57 OpenCL results, including barriers, events and images.

MIT; Python's standard library and the system OpenCL loader are sufficient.
No OpenCL version override or CPU device is accepted.
"""
import argparse
import array
import ctypes as C
import json
import math
import os
from pathlib import Path
import time

P, U, I, Z, Q = C.c_void_p, C.c_uint, C.c_int, C.c_size_t, C.c_uint64


class ImageFormat(C.Structure):
    _fields_ = [('order', U), ('kind', U)]


class ImageDesc(C.Structure):
    _fields_ = [('kind', U), ('width', Z), ('height', Z), ('depth', Z),
                ('array_size', Z), ('row_pitch', Z), ('slice_pitch', Z),
                ('mip_levels', U), ('samples', U), ('buffer', P)]


SOURCE = b'''
__kernel void integers(__global const uint *a, __global uint *b, uint n, uint salt) {
    size_t i = get_global_id(0); if (i >= n) return;
    uint v = a[i] ^ salt;
    for (uint r = 0; r < 8; r++) v = (v * 1664525u + 1013904223u) ^ (v >> 13);
    b[i] = v;
}
__kernel void floats(__global const float *a, __global float *b, uint n) {
    size_t i = get_global_id(0); if (i < n) b[i] = a[i] * 0.5f + 0.25f;
}
__kernel void sums(__global const uint *a, __global uint *b, uint n, __local uint *s) {
    size_t i = get_global_id(0); uint l = get_local_id(0);
    s[l] = i < n ? a[i] : 0; barrier(CLK_LOCAL_MEM_FENCE);
    for (uint d = get_local_size(0) / 2; d; d /= 2) {
        if (l < d) s[l] += s[l+d]; barrier(CLK_LOCAL_MEM_FENCE);
    }
    if (!l) b[get_group_id(0)] = s[0];
}
__kernel void pictures(read_only image2d_t src, write_only image2d_t dst) {
    int2 p = (int2)(get_global_id(0), get_global_id(1));
    uint4 c = read_imageui(src, p); write_imageui(dst, p, (uint4)(c.z, c.x, c.y, 255u));
}
'''


def checked(code, what):
    if code != 0:
        raise RuntimeError(f'{what}: OpenCL error {code}')


class OpenCL:
    def __init__(self):
        self.lib = C.CDLL('libOpenCL.so.1')
        self.resources = []
        signatures = {
            'clGetPlatformIDs': (I, [U, C.POINTER(P), C.POINTER(U)]),
            'clGetPlatformInfo': (I, [P, U, Z, P, C.POINTER(Z)]),
            'clGetDeviceIDs': (I, [P, Q, U, C.POINTER(P), C.POINTER(U)]),
            'clGetDeviceInfo': (I, [P, U, Z, P, C.POINTER(Z)]),
            'clCreateContext': (P, [P, U, C.POINTER(P), P, P, C.POINTER(I)]),
            'clCreateCommandQueue': (P, [P, P, Q, C.POINTER(I)]),
            'clCreateProgramWithSource': (P, [P, U, C.POINTER(C.c_char_p), P, C.POINTER(I)]),
            'clBuildProgram': (I, [P, U, C.POINTER(P), C.c_char_p, P, P]),
            'clGetProgramBuildInfo': (I, [P, P, U, Z, P, C.POINTER(Z)]),
            'clCreateKernel': (P, [P, C.c_char_p, C.POINTER(I)]),
            'clCreateBuffer': (P, [P, Q, Z, P, C.POINTER(I)]),
            'clCreateImage': (P, [P, Q, C.POINTER(ImageFormat), C.POINTER(ImageDesc), P, C.POINTER(I)]),
            'clSetKernelArg': (I, [P, U, Z, P]),
            'clEnqueueNDRangeKernel': (I, [P, P, U, P, C.POINTER(Z), C.POINTER(Z), U, C.POINTER(P), C.POINTER(P)]),
            'clEnqueueReadBuffer': (I, [P, P, U, Z, Z, P, U, C.POINTER(P), C.POINTER(P)]),
            'clEnqueueReadImage': (I, [P, P, U, C.POINTER(Z), C.POINTER(Z), Z, Z, P, U, C.POINTER(P), C.POINTER(P)]),
            'clWaitForEvents': (I, [U, C.POINTER(P)]),
            'clGetEventProfilingInfo': (I, [P, U, Z, P, C.POINTER(Z)]),
            'clFinish': (I, [P]),
        }
        for name in ('Context', 'CommandQueue', 'Program', 'Kernel', 'MemObject', 'Event'):
            signatures['clRelease' + name] = (I, [P])
        for name, (restype, argtypes) in signatures.items():
            f = getattr(self.lib, name)
            f.restype, f.argtypes = restype, argtypes
            setattr(self, name, f)

    def info(self, function, handle, field, kind=None):
        if kind is not None:
            value = kind()
            checked(function(handle, field, C.sizeof(value), C.byref(value), None), 'device info')
            return value.value
        size = Z()
        checked(function(handle, field, 0, None, C.byref(size)), 'info length')
        value = C.create_string_buffer(size.value)
        checked(function(handle, field, size, value, None), 'info string')
        return value.value.decode('utf-8', errors='replace').strip()

    def own(self, kind, function, *args):
        error = I()
        value = function(*args, C.byref(error))
        checked(error.value, function.__name__)
        if not value:
            raise RuntimeError(f'{function.__name__}: null handle')
        self.resources.append((kind, value))
        return value

    def close(self):
        for kind, value in reversed(self.resources):
            checked(getattr(self, 'clRelease' + kind)(value), 'release ' + kind)
        self.resources.clear()

    def select(self):
        count = U()
        checked(self.clGetPlatformIDs(0, None, C.byref(count)), 'platform enumeration')
        platforms = (P * count.value)()
        checked(self.clGetPlatformIDs(count, platforms, None), 'platform enumeration')
        for platform in platforms:
            if self.info(self.clGetPlatformInfo, platform, 0x902) != 'rusticl':
                continue
            count = U()
            code = self.clGetDeviceIDs(platform, 4, 0, None, C.byref(count))  # GPU only
            if code == -1:
                continue
            checked(code, 'GPU enumeration')
            devices = (P * count.value)()
            checked(self.clGetDeviceIDs(platform, 4, count, devices, None), 'GPU enumeration')
            for device in devices:
                name = self.info(self.clGetDeviceInfo, device, 0x102B)
                if 'Mali-G57' in name and 'Panfrost' in name:
                    self.device = P(device)
                    self.metadata = {
                        'platform': 'rusticl', 'device': name,
                        'device_type': self.info(self.clGetDeviceInfo, device, 0x1000, Q),
                        'device_version': self.info(self.clGetDeviceInfo, device, 0x102F),
                        'opencl_c_version': self.info(self.clGetDeviceInfo, device, 0x103D),
                        'driver_version': self.info(self.clGetDeviceInfo, device, 0x102D),
                        'images': bool(self.info(self.clGetDeviceInfo, device, 0x1016, U)),
                        'max_work_group': self.info(self.clGetDeviceInfo, device, 0x1004, Z),
                        'cpu_fallback': False,
                    }
                    return
        raise RuntimeError('No Rusticl Mali-G57 GPU; CPU/software fallbacks are not accepted')

    def start(self):
        self.select()
        self.context = self.own('Context', self.clCreateContext, None, 1, C.byref(self.device), None, None)
        self.queue = self.own('CommandQueue', self.clCreateCommandQueue, self.context, self.device, 2)
        self.program = self.own('Program', self.clCreateProgramWithSource, self.context, 1,
                                (C.c_char_p * 1)(SOURCE), None)
        code = self.clBuildProgram(self.program, 1, C.byref(self.device), b'-cl-std=CL1.2', None, None)
        if code:
            log = C.create_string_buffer(32768)
            self.clGetProgramBuildInfo(self.program, self.device, 0x1183, len(log), log, None)
            raise RuntimeError(f'OpenCL compiler error {code}: {log.value.decode(errors="replace")}')
        self.kernels = {name: self.own('Kernel', self.clCreateKernel, self.program, name.encode())
                        for name in ('integers', 'floats', 'sums', 'pictures')}
        if self.metadata['max_work_group'] < 64:
            raise RuntimeError('Expected work-group size 64 is unavailable')

    def buffer(self, data=None, size=None):
        host = None if data is None else (C.c_ubyte * len(data)).from_buffer_copy(data)
        return self.own('MemObject', self.clCreateBuffer, self.context,
                        1 | (32 if host is not None else 0), len(data) if data is not None else size, host)

    def run(self, name, arguments, dimensions, local=None):
        kernel = self.kernels[name]
        for index, arg in enumerate(arguments):
            checked(self.clSetKernelArg(kernel, index, 64 * 4 if arg is None else C.sizeof(arg),
                                        None if arg is None else C.byref(arg)), 'set argument')
        event = P()
        checked(self.clEnqueueNDRangeKernel(self.queue, kernel, len(dimensions), None,
                    (Z * len(dimensions))(*dimensions), None if local is None else (Z * len(local))(*local),
                    0, None, C.byref(event)), 'enqueue ' + name)
        self.resources.append(('Event', event.value))
        checked(self.clWaitForEvents(1, C.byref(event)), 'event completion')
        start, end = Q(), Q()
        for field, value in ((0x1282, start), (0x1283, end)):
            checked(self.clGetEventProfilingInfo(event, field, C.sizeof(value), C.byref(value), None),
                    'profiling timestamp')
        if end.value < start.value:
            raise RuntimeError('Invalid event profiling order')
        return end.value - start.value

    def read(self, buffer, size):
        data = C.create_string_buffer(size)
        checked(self.clEnqueueReadBuffer(self.queue, buffer, 1, 0, size, data, 0, None, None), 'buffer readback')
        return data.raw

    def check(self, seed):
        records = []
        for n in (1, 63, 64, 65, 1023, 65537):
            values = array.array('I', (((j * 2654435761) ^ seed) & 0xffffffff for j in range(n)))
            source, dest = self.buffer(values.tobytes()), self.buffer(size=n * 4)
            salt = (0xa5230214 + seed * 7919 + n) & 0xffffffff
            ns = self.run('integers', [P(source), P(dest), U(n), U(salt)], ((n + 63) // 64 * 64,), (64,))
            expected = array.array('I')
            for value in values:
                value ^= salt
                for _ in range(8):
                    value = ((value * 1664525 + 1013904223) ^ (value >> 13)) & 0xffffffff
                expected.append(value)
            if self.read(dest, n * 4) != expected.tobytes():
                raise RuntimeError(f'integer readback mismatch at length {n}')
            groups = (n + 63) // 64
            reduced = self.buffer(size=groups * 4)
            ns += self.run('sums', [P(source), P(reduced), U(n), None], (groups * 64,), (64,))
            sums = array.array('I', (sum(values[j:j+64]) & 0xffffffff for j in range(0, n, 64)))
            if self.read(reduced, groups * 4) != sums.tobytes():
                raise RuntimeError(f'local memory/barrier reduction mismatch at length {n}')
            records.append({'words': n, 'reduction_groups': groups, 'gpu_ns': ns})
        n = 65539
        values = array.array('f', (((j % 8192) - 4096) / 16.0 for j in range(n)))
        source, dest = self.buffer(values.tobytes()), self.buffer(size=n * 4)
        ns = self.run('floats', [P(source), P(dest), U(n)], ((n + 63) // 64 * 64,), (64,))
        got = array.array('f'); got.frombytes(self.read(dest, n * 4))
        error = max(abs(g - (v * 0.5 + 0.25)) for g, v in zip(got, values))
        if not all(math.isfinite(g) for g in got) or error > 1e-6:
            raise RuntimeError(f'float32 readback mismatch: {error}')
        if not self.metadata['images']:
            raise RuntimeError('Expected image support is unavailable')
        width, height = 257, 129
        pixels = bytes((j * 37 + seed) & 255 for j in range(width * height * 4))
        host = (C.c_ubyte * len(pixels)).from_buffer_copy(pixels)
        fmt = ImageFormat(0x10B5, 0x10DA)  # RGBA / UNSIGNED_INT8
        desc = ImageDesc(kind=0x10F1, width=width, height=height)  # IMAGE2D
        src = self.own('MemObject', self.clCreateImage, self.context, 4 | 32,
                       C.byref(fmt), C.byref(desc), host)
        dst = self.own('MemObject', self.clCreateImage, self.context, 2,
                       C.byref(fmt), C.byref(desc), None)
        ns += self.run('pictures', [P(src), P(dst)], (width, height))
        image = C.create_string_buffer(len(pixels))
        checked(self.clEnqueueReadImage(self.queue, dst, 1, (Z * 3)(0, 0, 0),
                    (Z * 3)(width, height, 1), 0, 0, image, 0, None, None), 'image readback')
        expected = bytearray(len(pixels))
        for j in range(0, len(pixels), 4):
            expected[j:j+4] = bytes((pixels[j+2], pixels[j], pixels[j+1], 255))
        if image.raw != expected:
            raise RuntimeError('image2d channel swizzle/readback mismatch')
        checked(self.clFinish(self.queue), 'queue finish')
        return {'integer_cases': records, 'float32_values': n, 'float32_max_error': error,
                'rgba_image_pixels': width * height, 'float_and_image_gpu_ns': ns,
                'integer_words': sum(r['words'] for r in records),
                'kernels': len(records) * 2 + 2, 'compiler_options': '-cl-std=CL1.2'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.seed < 2**31:
        parser.error('seed must fit a nonnegative signed 32-bit integer')
    for name in ('MESA_LOADER_DRIVER_OVERRIDE', 'MESA_GL_VERSION_OVERRIDE',
                 'MESA_GLES_VERSION_OVERRIDE', 'LIBGL_ALWAYS_SOFTWARE', 'RUSTICL_DEVICE_TYPE'):
        if os.environ.get(name):
            raise RuntimeError(f'Remove driver/version override {name} before qualification')
    os.environ['RUSTICL_ENABLE'] = 'panfrost'
    os.environ['OCL_ICD_VENDORS'] = '/etc/OpenCL/vendors/rusticl.icd'
    started = time.monotonic()
    cl = OpenCL()
    try:
        cl.start()
        result = cl.check(args.seed)
        result.update(cl.metadata)
        result.update(status='PASS', seed=args.seed, elapsed_s=round(time.monotonic() - started, 3),
                      boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        print(json.dumps(result, sort_keys=True), flush=True)
    finally:
        cl.close()


if __name__ == '__main__':
    main()
