#!/usr/bin/python3
"""Local touchscreen display controls and orientation-to-touch synchronization."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import cairo
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk

BL = Path('/sys/class/backlight/tzx-panel')
CONFIG = Path.home()/'.config/tzx-screen.json'
TOUCH = 'TZX GSL3670 candidate'
MATRICES = {'normal': (1, 0, 0, 0, 1, 0, 0, 0, 1),
            'left': (0, -1, 1, 1, 0, 0, 0, 0, 1),
            'right': (0, 1, 0, -1, 0, 1, 0, 0, 1),
            'inverted': (-1, 0, 1, 0, -1, 1, 0, 0, 1)}
p = argparse.ArgumentParser()
p.add_argument('--daemon', action='store_true')
p.add_argument('--rotate', choices=tuple(MATRICES))
p.add_argument('--set-brightness', type=int)
p.add_argument('--show-pattern', action='store_true')
a = p.parse_args()


def run(*cmd):
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=12)


def current_rotation():
    output = run('xrandr', '--query')
    line = next(line for line in output.splitlines() if line.startswith('DSI-1 connected'))
    head = line.split('(')[0].split()
    assert any(re.fullmatch(r'\d+x\d+\+\d+\+\d+', word) for word in head), line
    return next((r for r in ('left', 'right', 'inverted') if r in head), 'normal')


def sync_touch(rotation):
    matrix = tuple(float(v) for v in MATRICES[rotation])
    properties = run('xinput', 'list-props', TOUCH)
    values = next(line.split(':', 1)[1] for line in properties.splitlines()
                  if 'Coordinate Transformation Matrix (' in line)
    actual = tuple(float(v.strip()) for v in values.split(','))
    if actual != matrix:
        run('xinput', 'set-prop', TOUCH, 'Coordinate Transformation Matrix',
            *(str(v) for v in MATRICES[rotation]))


def save_rotation(rotation):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    # Commands and the session daemon can save at the same time. A unique
    # temporary file also prevents one writer from renaming another's file.
    with tempfile.NamedTemporaryFile(mode='w', prefix='tzx-screen-', suffix='.new',
                                     dir=CONFIG.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            json.dump({'rotation': rotation}, f)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
            tmp.replace(CONFIG)
            directory = os.open(CONFIG.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            tmp.unlink(missing_ok=True)


@contextmanager
def orientation_transaction():
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(CONFIG.with_suffix('.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def rotate(rotation):
    with orientation_transaction():
        run('xrandr', '--output', 'DSI-1', '--rotate', rotation)
        assert current_rotation() == rotation
        sync_touch(rotation)
        save_rotation(rotation)


def brightness(value):
    assert 1 <= value <= 100
    session = run('loginctl', 'show-user', str(os.getuid()), '-p', 'Display', '--value').strip()
    assert re.fullmatch(r'[a-zA-Z0-9]+', session), session
    proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE,
                                         None, 'org.freedesktop.login1',
                                         '/org/freedesktop/login1/session/'+session,
                                         'org.freedesktop.login1.Session', None)
    proxy.call_sync('SetBrightness', GLib.Variant('(ssu)', ('backlight', 'tzx-panel', value)),
                    Gio.DBusCallFlags.NONE, 8000, None)
    assert int((BL/'brightness').read_text()) == value


def daemon():
    # Xfce may change rotation from its own display dialog. Keep absolute touch
    # coordinates aligned even when that dialog, rather than this app, is used.
    remembered = None
    if CONFIG.exists():
        remembered = json.loads(CONFIG.read_text()).get('rotation')
    if remembered in MATRICES:
        try:
            rotate(remembered)
        except (OSError, AssertionError, subprocess.SubprocessError) as error:
            print('Restoring screen orientation:', error, file=sys.stderr, flush=True)
    last = None

    def tick():
        nonlocal last
        try:
            with orientation_transaction():
                rotation = current_rotation()
                sync_touch(rotation)
                if rotation != last:
                    save_rotation(rotation)
                    last = rotation
        except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
            print('Screen orientation:', error, file=sys.stderr, flush=True)
        return True

    tick()
    GLib.timeout_add_seconds(2, tick)
    Gtk.main()


def pattern():
    window = Gtk.Window(title='屏幕像素与颜色测试')
    window.fullscreen()
    overlay = Gtk.Overlay()
    area = Gtk.DrawingArea()

    def draw(widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        colors = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1), (0, 0, 0))
        for i, color in enumerate(colors):
            cr.set_source_rgb(*color)
            cr.rectangle(i*width/5, 0, width/5+1, height*.55)
            cr.fill()
        for i in range(16):
            cr.set_source_rgb(*(i/15,)*3)
            cr.rectangle(i*width/16, height*.55, width/16+1, height*.2)
            cr.fill()
        # Native one-pixel checkerboard reveals resampling or missing columns.
        tile = cairo.ImageSurface(cairo.FORMAT_RGB24, 2, 2)
        paint = cairo.Context(tile)
        paint.set_source_rgb(1, 1, 1)
        paint.rectangle(1, 0, 1, 1)
        paint.rectangle(0, 1, 1, 1)
        paint.fill()
        checkers = cairo.SurfacePattern(tile)
        checkers.set_extend(cairo.EXTEND_REPEAT)
        checkers.set_filter(cairo.FILTER_NEAREST)
        cr.set_source(checkers)
        cr.rectangle(0, int(height*.75), width, height)
        cr.fill()
        cr.set_line_width(1)
        cr.set_source_rgb(1, 0, 1)
        cr.rectangle(.5, .5, width-1, height-1)
        cr.stroke()
        return False

    area.connect('draw', draw)
    overlay.add(area)
    close = Gtk.Button(label='返回屏幕设置')
    close.set_halign(Gtk.Align.END)
    close.set_valign(Gtk.Align.START)
    close.set_margin_top(18)
    close.set_margin_end(18)
    close.set_size_request(160, 56)
    close.connect('clicked', lambda _: window.destroy())
    overlay.add_overlay(close)
    window.add(overlay)
    window.connect('key-press-event', lambda w, event: w.destroy() if event.keyval == 65307 else False)
    window.show_all()
    return window


def controls():
    window = Gtk.Window(title='屏幕设置')
    window.set_default_size(540, 390)
    window.set_border_width(22)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    window.add(box)
    label = Gtk.Label(label='屏幕亮度')
    label.set_halign(Gtk.Align.START)
    box.pack_start(label, False, False, 0)
    slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
    slider.set_value(max(1, int((BL/'brightness').read_text())))
    slider.set_size_request(-1, 58)
    box.pack_start(slider, False, False, 0)
    message = Gtk.Label()
    pending = None

    def apply():
        nonlocal pending
        pending = None
        try:
            brightness(round(slider.get_value()))
            message.set_text('')
        except (OSError, GLib.Error, AssertionError, subprocess.SubprocessError) as error:
            message.set_text('亮度设置失败，请重新打开屏幕设置。')
            print(error, file=sys.stderr, flush=True)
        return False

    def changed(_):
        nonlocal pending
        if pending is not None:
            GLib.source_remove(pending)
        pending = GLib.timeout_add(220, apply)

    slider.connect('value-changed', changed)
    grid = Gtk.Grid(column_spacing=12, row_spacing=12)
    for i, (title, rotation) in enumerate((('竖屏', 'normal'), ('横屏（向左）', 'left'),
                                         ('倒置', 'inverted'), ('横屏（向右）', 'right'))):
        button = Gtk.Button(label=title)
        button.set_size_request(230, 54)

        def click(_, selected=rotation):
            try:
                rotate(selected)
                message.set_text('')
            except (OSError, AssertionError, subprocess.SubprocessError) as error:
                message.set_text('方向切换失败，已保留当前方向。')
                print(error, file=sys.stderr, flush=True)

        button.connect('clicked', click)
        grid.attach(button, i % 2, i // 2, 1, 1)
    box.pack_start(grid, False, False, 0)
    row = Gtk.Box(spacing=12)
    test = Gtk.Button(label='颜色与像素测试')
    test.set_size_request(230, 54)
    test.connect('clicked', lambda _: pattern())
    row.pack_start(test, True, True, 0)
    off = Gtk.Button(label='熄屏（触摸唤醒）')
    off.set_size_request(230, 54)

    def blank(_):
        def later():
            run('xset', '+dpms')
            run('xset', 'dpms', 'force', 'off')
            return False
        GLib.timeout_add(700, later)

    off.connect('clicked', blank)
    row.pack_start(off, True, True, 0)
    box.pack_start(row, False, False, 0)
    box.pack_start(message, False, False, 0)
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    Gtk.main()


if a.daemon:
    daemon()
elif a.rotate:
    rotate(a.rotate)
elif a.set_brightness is not None:
    brightness(a.set_brightness)
elif a.show_pattern:
    window = pattern()
    window.connect('destroy', Gtk.main_quit)
    Gtk.main()
else:
    controls()
