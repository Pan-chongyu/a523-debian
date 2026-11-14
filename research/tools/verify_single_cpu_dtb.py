"""Independently compare every DT property after libfdt decompilation in WSL."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

root = Path(__file__).resolve().parents[1]
folder = root/'build/single-cpu-trial'
manifest = json.loads((folder/'linux-bundle.json').read_text())
dtb = folder/'board.dtb'
before = manifest['original_properties']
after = {}
data = dtb.read_bytes()
_,total,cursor,strings = struct.unpack_from('>4I',data)
stack=[]
while True:
    token = struct.unpack_from('>I',data,cursor)[0]; cursor += 4
    if token == 1:
        end=data.index(0,cursor); stack.append(data[cursor:end].decode()); cursor=(end+4)&~3
    elif token == 2:
        stack.pop()
    elif token == 3:
        length,nameoff=struct.unpack_from('>II',data,cursor); cursor+=8
        end=data.index(0,strings+nameoff); name=data[strings+nameoff:end].decode()
        after['/'.join(stack)+'/'+name] = data[cursor:cursor+length].hex()
        cursor=(cursor+length+3)&~3
    elif token == 4:
        pass
    elif token == 9:
        break
    else:
        raise AssertionError(token)
assert not stack and set(before)==set(after)
changed=[name for name in before if before[name]!=after[name]]
assert changed==['/chosen/bootargs'],changed
assert bytes.fromhex(after['/memory@40000000/reg']) == struct.pack('>4I',0,0x40000000,1,0)
output=subprocess.run(['dtc','-I','dtb','-O','dts',str(dtb)],capture_output=True,text=True,check=True)
(folder/'board-libfdt-verified.dts').write_text(output.stdout)
(folder/'dtc-warnings.txt').write_text(output.stderr)
args=subprocess.check_output(['fdtget','-t','s',str(dtb),'/chosen','bootargs'],text=True).strip()
assert args == manifest['bootargs_after'] and args.endswith(' maxcpus=1')
record={'dtc_decompile':'PASS','properties':len(after),'only_property_change':changed,
        'full_4gib_retained':True,'dtb_sha256':hashlib.sha256(data).hexdigest(),
        'bundle_sha256':manifest['sha256']}
(folder/'DTB_VERIFIED.json').write_text(json.dumps(record,indent=2)+'\n')
print('SINGLE_CPU_DTB_INDEPENDENT_VERIFY_PASS',json.dumps(record))
