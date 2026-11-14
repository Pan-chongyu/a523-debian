#!/usr/bin/env python3
"""Check advertised OpenCL C 3.0 int64/images, atomics and cross-queue events. MIT."""
import array
import ctypes as C
import json
import os
from pathlib import Path
import time

from opencl_check import OpenCL, ImageDesc, ImageFormat, checked, P, U, I, Q, Z

SOURCE = b'''
#ifndef __opencl_c_int64
#error int64 feature missing
#endif
#ifndef __opencl_c_read_write_images
#error read-write image feature missing
#endif
__kernel void wide(__global const ulong *a, __global ulong *b, uint n) {
    size_t i=get_global_id(0); if(i<n) b[i]=(a[i]*0x123456789abcdefUL+0xfedcba9876543210UL)^(a[i]>>17);
}
__kernel void totals(volatile __global uint *v, uint n) {
    uint i=get_global_id(0); if(i<n) atomic_add(v, (i*17u)^0xa523u);
}
__kernel void rwimage(read_write image2d_t img) {
    int2 p=(int2)(get_global_id(0),get_global_id(1));
    uint4 v=read_imageui(img,p); write_imageui(img,p,v^(uint4)(31,63,127,0));
}
'''


def main():
    for name in ('MESA_LOADER_DRIVER_OVERRIDE', 'MESA_GL_VERSION_OVERRIDE',
                 'MESA_GLES_VERSION_OVERRIDE', 'LIBGL_ALWAYS_SOFTWARE', 'RUSTICL_DEVICE_TYPE'):
        if os.environ.get(name):
            raise RuntimeError('Remove driver/version override: ' + name)
    os.environ.update(RUSTICL_ENABLE='panfrost', OCL_ICD_VENDORS='/etc/OpenCL/vendors/rusticl.icd')
    started, cl = time.monotonic(), OpenCL()
    try:
        cl.start()
        program = cl.own('Program', cl.clCreateProgramWithSource, cl.context, 1,
                         (C.c_char_p * 1)(SOURCE), None)
        error = cl.clBuildProgram(program, 1, C.byref(cl.device), b'-cl-std=CL3.0', None, None)
        if error:
            log = C.create_string_buffer(32768)
            cl.clGetProgramBuildInfo(program, cl.device, 0x1183, len(log), log, None)
            raise RuntimeError('OpenCL C 3.0 compiler: ' + log.value.decode(errors='replace'))
        cl.kernels = {name: cl.own('Kernel', cl.clCreateKernel, program, name.encode())
                      for name in ('wide', 'totals', 'rwimage')}
        n = 131071
        values = array.array('Q', ((j * 0x9e3779b97f4a7c15) & 0xffffffffffffffff for j in range(n)))
        source, dest = cl.buffer(size=n * 8), cl.buffer(size=n * 8)
        queue = cl.own('CommandQueue', cl.clCreateCommandQueue, cl.context, cl.device, 3)
        write = cl.lib.clEnqueueWriteBuffer
        write.restype, write.argtypes = I, [P, P, U, Z, Z, P, U, C.POINTER(P), C.POINTER(P)]
        flush = cl.lib.clFlush; flush.restype, flush.argtypes = I, [P]
        host = (C.c_ubyte * (n * 8)).from_buffer_copy(values.tobytes())
        write_event, compute_event = P(), P()
        checked(write(cl.queue, source, 0, 0, n * 8, host, 0, None, C.byref(write_event)), 'async write')
        cl.resources.append(('Event', write_event.value))
        kernel = cl.kernels['wide']
        for index, arg in enumerate((P(source), P(dest), U(n))):
            checked(cl.clSetKernelArg(kernel, index, C.sizeof(arg), C.byref(arg)), 'wide argument')
        checked(cl.clEnqueueNDRangeKernel(queue, kernel, 1, None, (Z * 1)((n + 63) // 64 * 64),
                    (Z * 1)(64), 1, C.byref(write_event), C.byref(compute_event)), 'cross-queue kernel')
        cl.resources.append(('Event', compute_event.value))
        checked(flush(cl.queue), 'flush producer queue'); checked(flush(queue), 'flush consumer queue')
        observed = C.create_string_buffer(n * 8)
        checked(cl.clEnqueueReadBuffer(cl.queue, dest, 1, 0, n * 8, observed,
                    1, C.byref(compute_event), None), 'cross-queue readback')
        expected = array.array('Q', (((v * 0x123456789abcdef + 0xfedcba9876543210) ^ (v >> 17)) &
                                     0xffffffffffffffff for v in values))
        if observed.raw != expected.tobytes():
            raise RuntimeError('int64/cross-queue-event mismatch')
        checked(cl.clFinish(queue), 'out-of-order queue finish')
        counter = cl.buffer(array.array('I', [0]).tobytes())
        atomic_n = 65537
        cl.run('totals', [P(counter), U(atomic_n)], ((atomic_n + 63) // 64 * 64,), (64,))
        expected_count = sum((j * 17) ^ 0xa523 for j in range(atomic_n)) & 0xffffffff
        if cl.read(counter, 4) != array.array('I', [expected_count]).tobytes():
            raise RuntimeError('global uint32 atomic_add mismatch')
        width, height = 127, 67
        pixels = bytes((j * 29 + 7) & 255 for j in range(width * height * 4))
        image_host = (C.c_ubyte * len(pixels)).from_buffer_copy(pixels)
        fmt = ImageFormat(0x10B5, 0x10DA)
        desc = ImageDesc(kind=0x10F1, width=width, height=height)
        image = cl.own('MemObject', cl.clCreateImage, cl.context, 1 | 32,
                       C.byref(fmt), C.byref(desc), image_host)
        cl.run('rwimage', [P(image)], (width, height))
        output = C.create_string_buffer(len(pixels))
        checked(cl.clEnqueueReadImage(cl.queue, image, 1, (Z * 3)(0, 0, 0),
                    (Z * 3)(width, height, 1), 0, 0, output, 0, None, None), 'read-write image readback')
        if output.raw != bytes(v ^ (31, 63, 127, 0)[j % 4] for j, v in enumerate(pixels)):
            raise RuntimeError('OpenCL C 3.0 read_write image mismatch')
        print(json.dumps(dict(status='PASS', **cl.metadata, compiler_options='-cl-std=CL3.0',
            int64_values=n, global_atomics=atomic_n, read_write_image_pixels=width * height,
            out_of_order_queue=True, cross_queue_event_dependencies=True,
            elapsed_s=round(time.monotonic()-started, 3),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())), flush=True)
    finally:
        cl.close()


if __name__ == '__main__':
    main()
