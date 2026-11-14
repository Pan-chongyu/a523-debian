"""Save a read-only X11 screenshot using the installed libX11 and stdlib."""
import ctypes as C
from pathlib import Path
import struct
import zlib

class XImage(C.Structure):
    _fields_ = [('width', C.c_int), ('height', C.c_int), ('xoffset', C.c_int),
                ('format', C.c_int), ('data', C.c_void_p), ('byte_order', C.c_int),
                ('bitmap_unit', C.c_int), ('bitmap_bit_order', C.c_int),
                ('bitmap_pad', C.c_int), ('depth', C.c_int), ('bytes_per_line', C.c_int),
                ('bits_per_pixel', C.c_int), ('red_mask', C.c_ulong),
                ('green_mask', C.c_ulong), ('blue_mask', C.c_ulong)]

x = C.CDLL('libX11.so.6')
x.XOpenDisplay.argtypes = [C.c_char_p]; x.XOpenDisplay.restype = C.c_void_p
x.XDefaultScreen.argtypes = [C.c_void_p]; x.XDefaultScreen.restype = C.c_int
x.XRootWindow.argtypes = [C.c_void_p, C.c_int]; x.XRootWindow.restype = C.c_ulong
x.XDisplayWidth.argtypes = [C.c_void_p, C.c_int]; x.XDisplayWidth.restype = C.c_int
x.XDisplayHeight.argtypes = [C.c_void_p, C.c_int]; x.XDisplayHeight.restype = C.c_int
x.XGetImage.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_ulong, C.c_int]
x.XGetImage.restype = C.POINTER(XImage)
x.XDestroyImage.argtypes = [C.POINTER(XImage)]
x.XCloseDisplay.argtypes = [C.c_void_p]
display = x.XOpenDisplay(None)
assert display, 'X11 display unavailable or authentication failed'
screen = x.XDefaultScreen(display)
width, height = x.XDisplayWidth(display, screen), x.XDisplayHeight(display, screen)
assert 0 < width <= 4096 and 0 < height <= 4096
image = x.XGetImage(display, x.XRootWindow(display, screen), 0, 0, width, height, C.c_ulong(-1), 2)
assert image
try:
    info = image.contents
    assert info.bits_per_pixel == 32 and info.byte_order == 0
    assert (info.red_mask, info.green_mask, info.blue_mask) == (0xff0000, 0xff00, 0xff)
    data = C.string_at(info.data, height * info.bytes_per_line)
    rows = bytearray()
    for row in range(height):
        pixels = data[row * info.bytes_per_line:row * info.bytes_per_line + width*4]
        rgb = bytearray(width*3)
        rgb[0::3], rgb[1::3], rgb[2::3] = pixels[2::4], pixels[1::4], pixels[0::4]
        rows.append(0); rows.extend(rgb)
    def chunk(tag, payload):
        return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', zlib.crc32(tag+payload))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')
    Path('/home/debian/desktop-capture.png').write_bytes(png)
    print('X11_SCREENSHOT', width, height, len(png))
finally:
    x.XDestroyImage(image); x.XCloseDisplay(display)
