"""Convert a reviewed vendor C firmware array to the mainline Silead format."""
import argparse, hashlib, json, re, struct
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('header',type=Path);p.add_argument('symbol');p.add_argument('output',type=Path)
a=p.parse_args()
source=a.header.read_text()
body=source.split(a.symbol+'[]',1)[1].split('{',1)[1].split('};',1)[0]
body=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S)
pairs=re.findall(r'\{\s*(0x[0-9a-fA-F]+|[0-9]+)\s*,\s*(0x[0-9a-fA-F]+|[0-9]+)\s*\}',body)
assert len(pairs)>1000
data=bytearray()
for off,val in pairs:
    off,val=int(off,0),int(val,0)
    assert off==0xf0 or (0<=off<=0x7c and off%4==0)
    data.extend(struct.pack('<II',off,val))
a.output.write_bytes(data)
manifest={'source_header':a.header.name,'symbol':a.symbol,'records':len(pairs),
          'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
          'status':'candidate, requires actual touch testing'}
a.output.with_suffix('.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
