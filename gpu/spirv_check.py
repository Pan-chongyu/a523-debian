#!/usr/bin/env python3
"""Execute a small, reproducible SPIR-V kernel through OpenCL IL. MIT.

This checks OpenCL's SPIR-V input; it does not provide a Vulkan driver.
Instruction numbers follow Khronos SPIRV-Headers' core grammar.
"""
import array
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct
import time

from opencl_check import OpenCL, checked, P, I, Z


def module_bytes():
    words = [0x07230203, 0x00010000, 0, 19, 0]

    def op(code, *operands):
        words.extend([((len(operands) + 1) << 16) | code, *operands])

    def string(value):
        value = value.encode() + b'\0'
        value += b'\0' * (-len(value) % 4)
        return struct.unpack('<' + 'I' * (len(value) // 4), value)

    op(17, 4)                           # Capability Addresses
    op(17, 6)                           # Capability Kernel
    op(17, 11)                          # Capability Int64
    op(14, 2, 2)                        # Physical64 / OpenCL memory model
    op(15, 6, 1, *string('fill'), 3)      # Kernel entry point and global ID interface
    op(3, 3, 102000)                     # OpenCL C 1.2
    op(71, 3, 11, 28)                   # BuiltIn GlobalInvocationId
    op(19, 4)                           # void
    op(21, 5, 64, 0)                    # ulong
    op(21, 6, 32, 0)                    # uint
    op(23, 7, 5, 3)                     # ulong3
    op(32, 8, 1, 7)                     # Input ulong3 pointer
    op(59, 8, 3, 1)                     # global invocation ID
    op(32, 9, 5, 6)                     # CrossWorkgroup uint pointer
    op(33, 10, 4, 9)                    # void function(global uint *)
    op(43, 6, 11, 0xa5231234)            # salt
    op(54, 4, 1, 0, 10)                 # function
    op(55, 9, 12)                       # output pointer
    op(248, 13)                         # basic block
    op(61, 7, 14, 3)                    # load ulong3 global ID
    op(81, 5, 15, 14, 0)                # extract X
    op(113, 6, 16, 15)                  # uint(X)
    op(128, 6, 17, 16, 11)              # X + salt
    op(67, 9, 18, 12, 15)               # output + X
    op(62, 18, 17)                      # store
    op(253)                             # return
    op(56)                              # function end
    return struct.pack('<' + 'I' * len(words), *words)


def main():
    for name in ('MESA_LOADER_DRIVER_OVERRIDE', 'MESA_GL_VERSION_OVERRIDE',
                 'MESA_GLES_VERSION_OVERRIDE', 'LIBGL_ALWAYS_SOFTWARE', 'RUSTICL_DEVICE_TYPE'):
        if os.environ.get(name):
            raise RuntimeError('Remove driver/version override: ' + name)
    os.environ.update(RUSTICL_ENABLE='panfrost', OCL_ICD_VENDORS='/etc/OpenCL/vendors/rusticl.icd')
    started, cl = time.monotonic(), OpenCL()
    try:
        cl.start()
        blob = module_bytes()
        function = cl.lib.clCreateProgramWithIL
        function.restype, function.argtypes = P, [P, P, Z, C.POINTER(I)]
        host = C.create_string_buffer(blob)
        program = cl.own('Program', function, cl.context, host, len(blob))
        code = cl.clBuildProgram(program, 1, C.byref(cl.device), b'', None, None)
        if code:
            log = C.create_string_buffer(32768)
            cl.clGetProgramBuildInfo(program, cl.device, 0x1183, len(log), log, None)
            raise RuntimeError(f'OpenCL IL build error {code}: ' + log.value.decode(errors='replace'))
        kernel = cl.own('Kernel', cl.clCreateKernel, program, b'fill')
        cl.kernels['fill'] = kernel
        n = 65536
        target = cl.buffer(size=n * 4)
        gpu_ns = cl.run('fill', [P(target)], (n,), (64,))
        expected = array.array('I', (i + 0xa5231234 for i in range(n)))
        if cl.read(target, n * 4) != expected.tobytes():
            raise RuntimeError('SPIR-V OpenCL kernel output mismatch')
        print(json.dumps(dict(status='PASS', **cl.metadata, api='OpenCL IL / SPIR-V 1.0',
            words_checked=n, gpu_ns=gpu_ns, module_sha256=hashlib.sha256(blob).hexdigest(),
            module_bytes=len(blob), vulkan_test=False, elapsed_s=round(time.monotonic()-started, 3),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())), flush=True)
    finally:
        cl.close()


if __name__ == '__main__':
    main()
