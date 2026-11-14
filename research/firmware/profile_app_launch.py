"""Time private application windows without closing the user's applications."""
import argparse
import collections
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import statistics
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--label', required=True)
p.add_argument('--rounds', type=int, default=3)
p.add_argument('--apps', nargs='+', default=['terminal', 'editor', 'browser'])
p.add_argument('--browser-cache', choices=('default','on'), default='default')
p.add_argument('--boost', action='store_true')
a = p.parse_args()
assert os.geteuid() == 0
assert 1 <= a.rounds <= 5
assert set(a.apps) <= {'terminal', 'editor', 'browser'}
env = None
for proc in Path('/proc').glob('[0-9]*'):
    try:
        if proc.stat().st_uid == 1000 and (proc/'comm').read_text().strip() == 'xfce4-session':
            values = dict(s.split('=', 1) for s in (proc/'environ').read_bytes().decode().split('\0') if '=' in s)
            env = {k: values[k] for k in ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR') if k in values}
            break
    except (OSError, ValueError):
        pass
assert env and env['DISPLAY'] == ':0'
os.environ.update(env)
x = C.CDLL('libX11.so.6')
x.XOpenDisplay.argtypes = [C.c_char_p]; x.XOpenDisplay.restype = C.c_void_p
x.XDefaultRootWindow.argtypes = [C.c_void_p]; x.XDefaultRootWindow.restype = C.c_ulong
x.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]; x.XInternAtom.restype = C.c_ulong
x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
    C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong), C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)]
x.XFree.argtypes = [C.c_void_p]
x.XCloseDisplay.argtypes = [C.c_void_p]
display = x.XOpenDisplay(None)
assert display
root = x.XDefaultRootWindow(display)
atoms = {s: x.XInternAtom(display, s.encode(), False) for s in ('_NET_CLIENT_LIST', '_NET_WM_PID', 'WM_CLASS', '_NET_WM_STATE', 'WM_PROTOCOLS', 'WM_DELETE_WINDOW')}
class MessageData(C.Union):
    _fields_ = [('b', C.c_char*20), ('s', C.c_short*10), ('l', C.c_long*5)]
class ClientMessage(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int),
        ('display', C.c_void_p), ('window', C.c_ulong), ('message_type', C.c_ulong),
        ('format', C.c_int), ('data', MessageData)]
class Event(C.Union):
    _fields_ = [('client', ClientMessage), ('padding', C.c_long*24)]
x.XSendEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(Event)]
x.XFlush.argtypes = [C.c_void_p]
# Window destruction races are ordinary during startup/teardown.
error_callback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda *_: 0)
x.XSetErrorHandler.argtypes = [C.c_void_p]
x.XSetErrorHandler(C.cast(error_callback, C.c_void_p))

def prop(window, name):
    kind, fmt, count, extra, data = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong(), C.c_void_p()
    rc = x.XGetWindowProperty(display, window, atoms[name], 0, 4096, False, 0,
        C.byref(kind), C.byref(fmt), C.byref(count), C.byref(extra), C.byref(data))
    try:
        if rc or not data.value:
            return []
        if fmt.value == 32:
            return list(C.cast(data, C.POINTER(C.c_ulong))[:count.value])
        if fmt.value == 8:
            return C.string_at(data, count.value).decode(errors='replace')
        return []
    finally:
        if data.value:
            x.XFree(data)

account = pwd.getpwnam('debian')
child_env = dict(os.environ, **env, HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name)
child_groups = os.getgrouplist(account.pw_name, account.pw_gid)
folder = Path('/home/debian/app-launch-profile')
folder.mkdir(exist_ok=True)
os.chown(folder, 1000, 1000)
profile = folder/'firefox'
profile.mkdir(exist_ok=True)
os.chown(profile, 1000, 1000)
browser_prefs = {
    'browser.shell.checkDefaultBrowser': False, 'browser.startup.homepage_override.mstone': 'ignore',
    'browser.startup.page': 0, 'browser.startup.homepage': 'about:blank',
    'datareporting.policy.dataSubmissionEnabled': False, 'toolkit.telemetry.enabled': False,
    'browser.newtabpage.enabled': False, 'network.captive-portal-service.enabled': False,
    'app.normandy.enabled': False, 'app.update.enabled': False,
}
browser_prefs['gfx.webrender.program-binary-disk']=a.browser_cache=='on'
prefs = '\n'.join('user_pref('+json.dumps(k)+', '+json.dumps(v)+');' for k, v in browser_prefs.items())+'\n'
(profile/'user.js').write_text(prefs)
os.chown(profile/'user.js', 1000, 1000)
commands = {
    'terminal': ['xfce4-terminal', '--disable-server', '--title=TZX launch timing', '--geometry=70x16',
        '-x', '/bin/sh', '-c', 'printf "Application launch timing test\\n"; sleep 90'],
    'editor': ['mousepad', '--disable-server'],
    'browser': ['firefox-esr', '--no-remote', '--profile', str(profile), '--new-window', 'about:blank'],
}
policies = [Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0, 4)]
def frequencies():
    values = []
    for policy in policies:
        try:
            values.append(int((policy/'scaling_cur_freq').read_text()))
        except OSError as error:
            if error.errno != 16:
                raise
            values.append(None)  # The cpufreq core reports EBUSY during a slow switch.
    return tuple(values)

def disk():
    return list(map(int, Path('/sys/block/mmcblk0/stat').read_text().split()))

def task_stats(pids):
    result = {}
    for pid in pids:
        try:
            proc = Path('/proc')/str(pid)
            fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
            result[pid] = {'state': fields[0], 'ppid': int(fields[1]),
                'cpu_ticks': int(fields[11])+int(fields[12]), 'processor': int(fields[36]),
                'wchan': (proc/'wchan').read_text().strip()}
        except (OSError, ValueError):
            pass
    return result

record = dict(label=a.label, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    browser_binary_disk_cache=a.browser_cache=='on',boost_requested=a.boost,
    policy=[{k: (p/k).read_text().strip() for k in ('scaling_governor', 'scaling_min_freq', 'scaling_max_freq')} for p in policies], samples=[])
try:
    for repeat in range(a.rounds):
        for name in a.apps:
            time.sleep(2)
            before = set(prop(root, '_NET_CLIENT_LIST'))
            before_disk = disk()
            freq_counts = collections.Counter()
            wait_counts = collections.Counter()
            processor_counts = collections.Counter()
            log = (folder/(a.label+'-'+name+'-'+str(repeat)+'.log')).open('w')
            started = time.monotonic()
            launch_command = (['/usr/local/bin/tzx-launch'] if a.boost else [])+commands[name]
            child = subprocess.Popen(launch_command, env=child_env, user=account.pw_uid,
                group=account.pw_gid, extra_groups=child_groups,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            mapped = None
            tasks = set([child.pid])
            next_scan = started
            try:
                while time.monotonic()-started < 35:
                    freq_counts[frequencies()] += 1
                    # This kernel omits /proc/PID/task/PID/children; identify only
                    # this dedicated process group without reading command lines.
                    if time.monotonic() >= next_scan:
                        for proc in Path('/proc').glob('[0-9]*'):
                            try:
                                pid = int(proc.name)
                                if os.getpgid(pid) == child.pid:
                                    tasks.add(pid)
                            except ProcessLookupError:
                                pass
                        next_scan = time.monotonic()+.2
                    stats = task_stats(tasks)
                    for v in stats.values():
                        wait_counts[v['state']+':'+v['wchan']] += 1
                        if v['state'] == 'R':
                            processor_counts[v['processor']] += 1
                    for window in set(prop(root, '_NET_CLIENT_LIST'))-before:
                        pid = prop(window, '_NET_WM_PID')
                        try:
                            ours = bool(pid) and os.getpgid(pid[0]) == child.pid
                        except ProcessLookupError:
                            ours = False
                        if ours:
                            tasks.add(pid[0])
                            mapped = {'window': window, 'pid': pid[0], 'class': prop(window, 'WM_CLASS').replace('\0', ' ')}
                            break
                    if mapped:
                        break
                    if child.poll() is not None:
                        raise RuntimeError((name, 'early exit', child.returncode, log.name))
                    time.sleep(.025)
                elapsed = time.monotonic()-started
                assert mapped, (name, 'window timeout', log.name, 'group', child.pid, 'tasks', tasks,
                    'new_clients', [(w, prop(w, '_NET_WM_PID'), prop(w, 'WM_CLASS')) for w in set(prop(root, '_NET_CLIENT_LIST'))-before])
                end_disk = disk()
                item = dict(app=name, repeat=repeat, window_visible_seconds=round(elapsed, 4),
                    window=mapped, frequency_samples=[dict(khz=list(k), count=v) for k, v in freq_counts.items()],
                    wait_samples=dict(wait_counts), runnable_cpu_samples=dict(processor_counts),
                    storage_read_bytes=(end_disk[2]-before_disk[2])*512,
                    storage_read_ms=end_disk[3]-before_disk[3], main_process=task_stats([mapped['pid']]))
                record['samples'].append(item)
                (folder/(a.label+'.json')).write_text(json.dumps(record, indent=2)+'\n')
                print('APP_LAUNCH_SAMPLE', json.dumps(item), flush=True)
                time.sleep(.4)
            finally:
                if mapped and child.poll() is None:
                    event=Event()
                    event.client.type=33
                    event.client.display=display
                    event.client.window=mapped['window']
                    event.client.message_type=atoms['WM_PROTOCOLS']
                    event.client.format=32
                    event.client.data.l[0]=atoms['WM_DELETE_WINDOW']
                    event.client.data.l[1]=0
                    assert x.XSendEvent(display,mapped['window'],False,0,C.byref(event))
                    x.XFlush(display)
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    try:os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:child.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
                    raise RuntimeError(('test window did not exit cleanly', name))
                log.close()
                time.sleep(.5)
    record['summary'] = {name: dict(seconds=[s['window_visible_seconds'] for s in record['samples'] if s['app']==name],
        median_seconds=statistics.median(s['window_visible_seconds'] for s in record['samples'] if s['app']==name)) for name in a.apps}
    (folder/(a.label+'.json')).write_text(json.dumps(record, indent=2)+'\n')
    print('APP_LAUNCH_SUMMARY', json.dumps(record['summary']), flush=True)
finally:
    x.XCloseDisplay(display)
