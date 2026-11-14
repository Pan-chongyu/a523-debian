#!/usr/bin/env python3
"""Verify native Firefox WebGL 1/2 with a disposable profile and graceful exit. MIT."""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import socket
import subprocess
import tempfile
import time

WEBGL = r'''
const done = arguments[arguments.length - 1];
(async () => {
  const results = [];
  document.body.style.background = '#182238';
  document.body.style.color = 'white';
  document.body.textContent = 'Mali-G57 WebGL verification';
  for (const api of ['webgl', 'webgl2']) {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 64; document.body.appendChild(canvas);
    const gl = canvas.getContext(api, {antialias: false, preserveDrawingBuffer: true,
                                      failIfMajorPerformanceCaveat: true});
    if (!gl) throw Error(api + ' unavailable without a major performance caveat');
    let lost = false; canvas.addEventListener('webglcontextlost', () => {lost = true;});
    const debug = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null;
    // Firefox can sanitize this webpage-visible string (for example to
    // "Mali-G51, or similar"). Native hardware is checked separately through
    // privileged Troubleshoot data; keep browser privacy defaults intact.
    if (!renderer || /llvmpipe|softpipe|swiftshader|software/i.test(renderer))
      throw Error('Software or missing WebGL renderer: ' + renderer);
    const es3 = api === 'webgl2';
    const vertex = es3 ? '#version 300 es\nin vec2 p; void main(){gl_Position=vec4(p,0.0,1.0);}' :
                         'attribute vec2 p; void main(){gl_Position=vec4(p,0.0,1.0);}';
    const fragment = es3 ? '#version 300 es\nprecision highp float; uniform vec4 c; out vec4 o; void main(){o=c;}' :
                           'precision highp float; uniform vec4 c; void main(){gl_FragColor=c;}';
    const program = gl.createProgram();
    for (const [kind, source] of [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]]) {
      const shader = gl.createShader(kind); gl.shaderSource(shader, source); gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(shader));
      gl.attachShader(program, shader); gl.deleteShader(shader);
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), gl.STATIC_DRAW);
    const p = gl.getAttribLocation(program, 'p');
    gl.enableVertexAttribArray(p); gl.vertexAttribPointer(p, 2, gl.FLOAT, false, 0, 0);
    const c = gl.getUniformLocation(program, 'c'); const pixel = new Uint8Array(4);
    const started = performance.now();
    for (let frame = 0; frame < 120; frame++) {
      const expected = [(frame * 37) % 256, (frame * 19) % 256, (frame * 73) % 256, 255];
      gl.uniform4f(c, ...expected.map(v => v / 255)); gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.readPixels(32, 32, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      if (pixel.some((v, i) => Math.abs(v - expected[i]) > 1))
        throw Error(api + ' pixel mismatch at frame ' + frame + ': ' + pixel);
      if (lost || gl.getError() !== gl.NO_ERROR) throw Error(api + ' context lost or GL error');
      await new Promise(resolve => requestAnimationFrame(resolve));
    }
    results.push({api, renderer, version: gl.getParameter(gl.VERSION),
      shading_language: gl.getParameter(gl.SHADING_LANGUAGE_VERSION), frames_checked: 120,
      elapsed_ms: performance.now() - started, status: 'PASS'});
    gl.deleteBuffer(buffer); gl.deleteProgram(program);
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    canvas.remove();
  }
  return results;
})().then(value => done({status: 'PASS', apis: value})).catch(error => done({status: 'FAIL', error: String(error)}));
'''


class Marionette:
    def __init__(self, sock):
        self.socket, self.serial = sock, 0

    def receive(self):
        header = bytearray()
        while True:
            char = self.socket.recv(1)
            if not char:
                raise RuntimeError('Firefox closed the control connection')
            if char == b':':
                break
            header += char
            if len(header) > 12:
                raise RuntimeError('Invalid Marionette header')
        remaining = int(header)
        if not 0 < remaining < 2_000_000:
            raise RuntimeError('Invalid Marionette response size')
        chunks = []
        while remaining:
            chunk = self.socket.recv(min(remaining, 65536))
            if not chunk:
                raise RuntimeError('Truncated Firefox response')
            chunks.append(chunk); remaining -= len(chunk)
        return json.loads(b''.join(chunks))

    def call(self, method, parameters):
        self.serial += 1
        request = json.dumps([0, self.serial, method, parameters]).encode()
        self.socket.sendall(str(len(request)).encode() + b':' + request)
        reply = self.receive()
        if reply[:2] != [1, self.serial] or reply[2] is not None:
            raise RuntimeError('Firefox command failed: ' + str(reply))
        return reply[3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--user', default='debian')
    args = p.parse_args()
    if os.geteuid() != 0:
        p.error('root is needed to enter the existing desktop session')
    account = pwd.getpwnam(args.user)
    if account.pw_uid == 0:
        p.error('use an unprivileged desktop account')
    session = None
    for process in Path('/proc').glob('[0-9]*'):
        try:
            if process.stat().st_uid == account.pw_uid and (process / 'comm').read_text().strip() == 'xfce4-session':
                session = dict(item.split('=', 1) for item in (process / 'environ').read_bytes().decode().split('\0') if '=' in item)
                break
        except (OSError, ProcessLookupError):
            continue
    if session is None:
        raise RuntimeError('No running XFCE session for this user')
    environment = dict(os.environ)
    environment.update({name: session[name] for name in ('DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR',
                                                        'DBUS_SESSION_BUS_ADDRESS') if name in session})
    environment['MOZ_REMOTE_ALLOW_SYSTEM_ACCESS'] = '1'
    # Bind an unused loopback port; do not attach to any existing browser profile.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
    profile = Path(tempfile.mkdtemp(prefix='tzx-webgl-', dir=account.pw_dir))
    os.chown(profile, account.pw_uid, account.pw_gid)
    prefs = {'marionette.port': port, 'remote.prefs.recommended': False,
             'browser.shell.checkDefaultBrowser': False, 'browser.startup.page': 0,
             'browser.startup.homepage_override.mstone': 'ignore', 'browser.newtabpage.enabled': False,
             'datareporting.policy.dataSubmissionEnabled': False, 'toolkit.telemetry.enabled': False,
             'network.captive-portal-service.enabled': False, 'network.connectivity-service.enabled': False}
    (profile / 'user.js').write_text(''.join('user_pref(' + json.dumps(k) + ',' + json.dumps(v) + ');\n'
                                          for k, v in prefs.items()))
    os.chown(profile / 'user.js', account.pw_uid, account.pw_gid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    record = {'status': 'RUNNING', 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'driver_overrides': False, 'disposable_profile': True}
    started, child, sock, client = time.monotonic(), None, None, None
    with args.output.with_suffix('.browser.log').open('w') as log:
        try:
            child = subprocess.Popen(['runuser', '-u', args.user, '--', 'firefox-esr', '--no-remote',
                                      '--marionette', '--profile', str(profile), '--width', '640',
                                      '--height', '480', 'about:blank'], env=environment,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            while time.monotonic() - started < 90:
                try:
                    sock = socket.create_connection(('127.0.0.1', port), timeout=2)
                    sock.settimeout(120); break
                except OSError:
                    if child.poll() is not None:
                        raise RuntimeError('Firefox exited before the API test')
                    time.sleep(.2)
            if sock is None:
                raise RuntimeError('Firefox control interface timed out')
            client = Marionette(sock)
            record['protocol'] = client.receive()
            client.call('WebDriver:NewSession', {'capabilities': {'alwaysMatch': {'pageLoadStrategy': 'normal'}}})
            client.call('Marionette:SetContext', {'value': 'chrome'})
            graphics = client.call('WebDriver:ExecuteAsyncScript', {'script': '''
              const done=arguments[arguments.length-1];
              const {Troubleshoot}=ChromeUtils.importESModule("resource://gre/modules/Troubleshoot.sys.mjs");
              Troubleshoot.snapshot().then(s=>done({version:s.application.version,graphics:{
                compositor:s.graphics.windowLayerManagerType,accelerated_windows:s.graphics.numAcceleratedWindows,
                webgl1:s.graphics.webgl1Renderer,webgl2:s.graphics.webgl2Renderer}}));''',
              'args': [], 'newSandbox': True, 'sandbox': 'default', 'scriptTimeout': 60000})
            record['firefox'] = graphics.get('value', graphics)
            native = record['firefox']['graphics']
            if any('Mali-G57 (Panfrost)' not in native[name] for name in ('webgl1', 'webgl2')):
                raise RuntimeError('Firefox internal renderer is not the native Mali-G57')
            client.call('Marionette:SetContext', {'value': 'content'})
            data = client.call('WebDriver:ExecuteAsyncScript', {'script': WEBGL, 'args': [],
                'newSandbox': True, 'sandbox': 'default', 'scriptTimeout': 110000})
            record['webgl'] = data.get('value', data)
            if record['webgl'].get('status') != 'PASS':
                raise RuntimeError(str(record['webgl']))
            client.call('Marionette:Quit', {'flags': ['eAttemptQuit']})
            child.wait(timeout=30)
            if child.returncode:
                raise RuntimeError('Firefox did not exit cleanly')
            record.update(status='PASS', clean_exit=True)
        except BaseException as error:
            record.update(status='FAIL', error=repr(error))
            raise
        finally:
            if child is not None and child.poll() is None and client is not None:
                try:
                    client.call('Marionette:Quit', {'flags': ['eAttemptQuit']})
                    child.wait(timeout=30)
                    record['cleanup_graceful'] = child.returncode == 0
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    record['cleanup_graceful'] = False
            if sock is not None:
                sock.close()
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=10)
            record['elapsed_s'] = round(time.monotonic()-started, 3)
            args.output.write_text(json.dumps(record, indent=2) + '\n')
            # Only the unique profile created above is removed, after Firefox has exited.
            if profile.parent == Path(account.pw_dir) and profile.name.startswith('tzx-webgl-'):
                shutil.rmtree(profile)
            print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
