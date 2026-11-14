"""Build a bounded LZ4 boot entry from the pinned, installed raw kernel.

Run in WSL with its packaged liblz4 and AArch64 cross compiler. No kernel or
driver sources change. The separate composer preserves existing boot slots.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

root = Path(__file__).resolve().parents[1]
out = root/'build/boot-compact'
out.mkdir(exist_ok=True)
base = root/'build/boot-logo'
bundle = (base/'linux-bundle.bin').read_bytes()
manifest = json.loads((base/'linux-bundle.json').read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(bundle) == manifest['sha256'] == '828347d9746d086bfe966a2b633c444ea0c9c42b80fe30621f7553c5467b6f3e'
item = manifest['items'][0]
offset = (item['lba']-manifest['start_lba'])*512
raw = bundle[offset:offset+item['bytes']]
assert sha(raw) == item['sha256'] == '470dd0c350c7ef7aad392eac3a35237672862f0fffdacea8da4e6adb6740e6e4'
library = ctypes.CDLL('liblz4.so.1')
library.LZ4_compressBound.argtypes = [ctypes.c_int]
library.LZ4_compress_HC.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
library.LZ4_decompress_safe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
capacity = library.LZ4_compressBound(len(raw))
buffer = ctypes.create_string_buffer(capacity)
size = library.LZ4_compress_HC(raw, buffer, len(raw), capacity, 12)
assert size > 0
packed = buffer.raw[:size]
decoded = ctypes.create_string_buffer(len(raw))
assert library.LZ4_decompress_safe(packed, decoded, len(packed), len(raw)) == len(raw)
assert decoded.raw == raw
(out/'kernel.lz4-block').write_bytes(struct.pack('<8s6I', b'A523LZ4\0', 1, len(raw), len(packed), zlib.crc32(raw), 0, 0)+packed)
(out/'Image').write_bytes(raw)
(out/'compact_config.h').write_text(f'#define COMPACT_RAW {len(raw)}U\n#define COMPACT_PACKED {len(packed)}U\n#define COMPACT_CRC 0x{zlib.crc32(raw):08x}U\n')
flags = ['-O2', '-march=armv8-a+crc', '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding',
         '-fno-builtin', '-fno-stack-protector', '-fno-pie', '-fno-asynchronous-unwind-tables',
         '-Wall', '-Wextra', '-Werror', '-I'+str(out), '-I'+str(root/'firmware')]
subprocess.run(['aarch64-linux-gnu-gcc', *flags, '-static', '-nostdlib', '-nostartfiles', '-no-pie',
    '-Wl,--build-id=none', '-Wl,-T,'+str(root/'firmware/compact_entry.ld'),
    str(root/'firmware/compact_entry.S'), str(root/'firmware/compact_boot.c'), str(root/'firmware/compact_lz4.c'),
    '-o', str(out/'linux-entry.elf')], check=True)
subprocess.run(['aarch64-linux-gnu-objcopy', '-O', 'binary', str(out/'linux-entry.elf'), str(out/'linux-entry.bin')], check=True)
assert (out/'linux-entry.bin').stat().st_size < 0x10000
with (out/'linux-entry.disassembly').open('w') as stream:
    subprocess.run(['aarch64-linux-gnu-objdump', '-d', str(out/'linux-entry.elf')], stdout=stream, check=True)
subprocess.run(['aarch64-linux-gnu-gcc', *flags, '-static', '-fno-pie', '-no-pie',
    str(root/'tools/test_compact_lz4.c'), str(root/'firmware/compact_lz4.c'),
    '-o', str(out/'test-compact-lz4')], check=True)
test = subprocess.check_output(['qemu-aarch64-static', '-cpu', 'max', str(out/'test-compact-lz4'),
                               str(out/'kernel.lz4-block'), str(out/'Image')], text=True, timeout=90)
assert 'ARM64_PRODUCTION_KERNEL_LZ4_AND_MALFORMED_INPUTS_PASS' in test
(out/'decoder-test.txt').write_text(test)
symbols = subprocess.check_output(['aarch64-linux-gnu-nm', '-n', str(out/'linux-entry.elf')], text=True)
(out/'linux-entry.symbols.txt').write_text(symbols)
print(test, end='')
print(json.dumps(dict(kernel_raw_bytes=len(raw), kernel_packed_bytes=len(packed),
                      entry_bytes=(out/'linux-entry.bin').stat().st_size)))
