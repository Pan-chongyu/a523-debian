"""Append maxcpus=1 only, preserving all four non-DTB payloads in a new slot."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parents[1]
folder = root/'build/single-cpu-trial'
folder.mkdir(exist_ok=True)
assert not any(folder.iterdir())
old_manifest = json.loads((root/'build/cpufreq-framework-kernel/linux-bundle.json').read_text())
old = (root/'build/cpufreq-framework-kernel/linux-bundle.bin').read_bytes()
sha = lambda data:hashlib.sha256(data).hexdigest()
assert sha(old) == old_manifest['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
item = old_manifest['items'][1]
start = (item['lba']-65536)*512
dtb = bytearray(old[start:start+item['bytes']])
magic,total,structure,strings = struct.unpack_from('>4I',dtb)
assert magic == 0xd00dfeed and total <= len(dtb) and structure < strings
assert not any(dtb[total:])
dtb = dtb[:total]
cursor,stack,matches = structure,[],[]
properties = {}
while True:
    token = struct.unpack_from('>I',dtb,cursor)[0]
    cursor += 4
    if token == 1:
        end = dtb.index(0,cursor)
        stack.append(dtb[cursor:end].decode())
        cursor = (end+4)&~3
    elif token == 2:
        stack.pop()
    elif token == 3:
        length,name_offset = struct.unpack_from('>II',dtb,cursor)
        cursor += 8
        end = dtb.index(0,strings+name_offset)
        name = dtb[strings+name_offset:end].decode()
        path = '/'.join(stack)
        properties[path+'/'+name] = bytes(dtb[cursor:cursor+length]).hex()
        if path == '/chosen' and name == 'bootargs':
            matches.append((cursor,length))
        cursor = (cursor+length+3)&~3
    elif token == 4:
        pass
    elif token == 9:
        break
    else:
        raise AssertionError(token)
assert len(matches) == 1 and not stack
position,length = matches[0]
before_args = bytes(dtb[position:position+length])
assert before_args[-1:] == b'\0' and b'maxcpus=' not in before_args and b'nosmp' not in before_args
after_args = before_args[:-1]+b' maxcpus=1\0'
padding = lambda data:data+bytes(-len(data)%4)
old_region = (length+3)&~3
replacement = padding(after_args)
delta = len(replacement)-old_region
dtb[position:position+old_region] = replacement
struct.pack_into('>I',dtb,position-8,len(after_args))
struct.pack_into('>I',dtb,4,total+delta)
struct.pack_into('>I',dtb,12,strings+delta)
struct.pack_into('>I',dtb,36,struct.unpack_from('>I',dtb,36)[0]+delta)
assert len(dtb) == total+delta
(folder/'board.dtb').write_bytes(dtb)
header = bytearray(512)
header[:8] = b'A523BND1'
struct.pack_into('<II',header,8,1,5)
bundle = bytearray(512)
items = []
for index,item in enumerate(old_manifest['items']):
    offset = (item['lba']-65536)*512
    saved = old[offset:offset+item['bytes']]
    assert sha(saved) == item['sha256']
    data = bytes(dtb) if index == 1 else saved
    lba = 98304+len(bundle)//512
    block = data+bytes(-len(data)%512)
    struct.pack_into('<6I',header,32+index*24,lba,len(data),int(item['load_address'],16),
                     zlib.crc32(block),0,0)
    bundle.extend(block)
    items.append(dict(file=item['file'],lba=lba,bytes=len(data),load_address=item['load_address'],sha256=sha(data)))
struct.pack_into('<I',header,16,zlib.crc32(header))
bundle[:512] = header
assert 98304+len(bundle)//512 < 131072
record = dict(start_lba=98304,header_lba=4096,items=items,bytes=len(bundle),sectors=len(bundle)//512,
    sha256=sha(bundle),original_bundle_sha256=sha(old),changed_payloads=['board.dtb'],
    hardware_boot_verified=False,purpose='diagnostic maxcpus=1, preserve full 4GiB',
    bootargs_before=before_args[:-1].decode(),bootargs_after=after_args[:-1].decode(),
    dtb_structure_growth=delta,original_properties=properties)
(folder/'linux-bundle.bin').write_bytes(bundle)
(folder/'linux-bundle.json').write_text(json.dumps(record,indent=2)+'\n')
print('SINGLE_CPU_BUNDLE_COMPOSED',json.dumps({k:v for k,v in record.items() if k != 'original_properties'},indent=2))
