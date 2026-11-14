"""Stream target kernel diagnostics to the host across a bounded GPU trial."""
import argparse
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=120)
parser.add_argument('--output', required=True)
parser.add_argument('--unit', help='Follow one transient service instead of the kernel ring')
args = parser.parse_args()
assert 1 <= args.seconds <= 600
assert Path(args.output).name == args.output
if args.unit:
    assert re.fullmatch(r'tzx-[a-z0-9-]+\.service', args.unit)
private = root/'private'
password = re.search(r'^Password: (.+)$', (private/'initial-login.txt').read_text(), re.M).group(1)
known = private/'tablet_known_hosts'
assert known.exists()  # Reuse the pinned key; do not modify another SSH call's file.
remote = ("exec journalctl -b -f -n 0 --no-pager -u " + args.unit if args.unit else
          'exec dmesg --follow --time-format iso')
command = ['ssh', '-i', str(private/'tzx-host-ed25519'), '-o', 'BatchMode=yes',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(known),
           '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=3',
           '-o', 'ServerAliveCountMax=2', 'debian@192.168.77.2',
           "sudo -S -p '' /bin/sh -c '" + remote + "'"]
process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
process.stdin.write(password+'\n')
process.stdin.flush()
process.stdin.close()
lines = queue.Queue()

def receive():
    for line in process.stdout:
        lines.put(line.replace(password, '<redacted>'))
    lines.put(None)

threading.Thread(target=receive, daemon=True).start()
count = 0
deadline = time.monotonic()+args.seconds
with (root/'evidence'/args.output).open('w', encoding='utf-8', buffering=1) as output:
    output.write('HOST_KERNEL_CAPTURE_STARTED\n')
    print('HOST_KERNEL_CAPTURE_STARTED', flush=True)
    try:
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                break
            output.write(line)
            count += 1
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        while not lines.empty():
            line = lines.get()
            if line is not None:
                output.write(line)
                count += 1
    output.write('HOST_KERNEL_CAPTURE_END exit='+str(process.returncode)+' lines='+str(count)+'\n')
print('HOST_KERNEL_CAPTURE_END', process.returncode, 'lines', count, flush=True)
