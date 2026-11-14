"""Install one small reviewed configuration file through authenticated serial."""
import argparse,base64,hashlib,re,time
from pathlib import Path
from debian_console import open_shell,ROOT
p=argparse.ArgumentParser();p.add_argument('--file',type=Path,required=True)
p.add_argument('--remote',required=True);p.add_argument('--mode',default='644')
a=p.parse_args()
assert re.fullmatch(r'/(?:etc|usr/local|root|var/lib|tmp|home/debian)/[a-zA-Z0-9_./@-]+',a.remote) and '..' not in a.remote
assert re.fullmatch(r'[0-7]{3}',a.mode)
raw=a.file.read_bytes();encoded=base64.b64encode(raw).decode();digest=hashlib.sha256(raw).hexdigest()
parent=str(Path(a.remote).parent).replace('\\','/')
command=f"mkdir -p {parent}; printf '%s' '{encoded}' | base64 -d > {a.remote}; chmod {a.mode} {a.remote}; sha256sum {a.remote}\n"
assert len(command)<3900,'Use SSH for large files'
link,password=open_shell(True)
try:
    link.write(command.encode());out=bytearray();end=time.monotonic()+10
    while time.monotonic()<end:
        out.extend(link.read(16384))
        if digest.encode() in out:break
    assert digest.encode() in out,out.decode(errors='replace')[-1000:]
    print(f'Installed {a.remote}: SHA256 {digest}')
finally:
    link.write(b'exit\n');time.sleep(.2);link.write(b'exit\n');time.sleep(.2);link.close()
