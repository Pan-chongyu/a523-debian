"""Change only #5's DT memory extent; keep all eight CPUs and original BL31."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parents[1]
folder = root/'build/k5-low-window-3g'
folder.mkdir(exist_ok=True)
assert not any(folder.iterdir())
old_manifest = json.loads((root/'build/cpufreq-framework-kernel/linux-bundle.json').read_text())
old = (root/'build/cpufreq-framework-kernel/linux-bundle.bin').read_bytes()
sha = lambda data:hashlib.sha256(data).hexdigest()
assert sha(old) == old_manifest['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
item = old_manifest['items'][1]
start = (item['lba']-65536)*512
before = old[start:start+item['bytes']]
dtb = bytearray(before)
magic,total,structure,strings = struct.unpack_from('>4I',dtb)
assert magic == 0xd00dfeed and total <= len(dtb)

def properties(data):
    cursor,stack,result,positions = structure,[],{},{}
    while True:
        token = struct.unpack_from('>I',data,cursor)[0]
        cursor += 4
        if token == 1:
            end = data.index(0,cursor)
            stack.append(data[cursor:end].decode())
            cursor = (end+4)&~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length,nameoff = struct.unpack_from('>II',data,cursor)
            cursor += 8
            end = data.index(0,strings+nameoff)
            key = '/'.join(stack)+'/'+data[strings+nameoff:end].decode()
            assert key not in result
            result[key] = bytes(data[cursor:cursor+length])
            positions[key] = cursor
            cursor = (cursor+length+3)&~3
        elif token == 4:
            pass
        elif token == 9:
            break
        else:
            raise AssertionError(token)
    assert not stack
    return result,positions

props,positions = properties(dtb)
key = '/memory@40000000/reg'
assert props[key] == struct.pack('>4I',0,0x40000000,1,0)
new_reg = struct.pack('>4I',0,0x40000000,0,0xc0000000)
dtb[positions[key]:positions[key]+16] = new_reg
after_props,_ = properties(dtb)
assert {p for p in props if props[p] != after_props[p]} == {key}
assert after_props[key] == new_reg and props.keys() == after_props.keys()
assert len(dtb) == len(before) == 21492
(folder/'board.dtb').write_bytes(dtb)
header = bytearray(512)
header[:8] = b'A523BND1'
struct.pack_into('<II',header,8,1,5)
bundle,items = bytearray(512),[]
for index,item in enumerate(old_manifest['items']):
    offset = (item['lba']-65536)*512
    saved = old[offset:offset+item['bytes']]
    assert sha(saved) == item['sha256']
    data = bytes(dtb) if index == 1 else saved
    lba = 98304+len(bundle)//512
    block = data+bytes(-len(data)%512)
    struct.pack_into('<6I',header,32+index*24,lba,len(data),int(item['load_address'],16),zlib.crc32(block),0,0)
    bundle.extend(block)
    items.append(dict(file=item['file'],lba=lba,bytes=len(data),load_address=item['load_address'],sha256=sha(data)))
struct.pack_into('<I',header,16,zlib.crc32(header))
bundle[:512] = header
assert len(bundle) == len(old) == 14876672 and 98304+len(bundle)//512 < 131072
manifest = dict(start_lba=98304,header_lba=4096,items=items,bytes=len(bundle),sectors=len(bundle)//512,
    sha256=sha(bundle),original_bundle_sha256=sha(old),changed_payloads=['board.dtb'],
    hardware_boot_verified=False,purpose='diagnostic low 3GiB physical address window; not final RAM qualification',
    ram_before_bytes=1<<32,ram_after_bytes=3<<30,physical_end_exclusive='0x100000000',
    dt_properties_checked=len(props),only_changed_dt_property=key,
    bootargs_unchanged=props['/chosen/bootargs'].decode().rstrip('\0'))
(folder/'linux-bundle.bin').write_bytes(bundle)
(folder/'linux-bundle.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')

installer = (root/'firmware/install_single_cpu_trial.py').read_text()
replacements = {
    'Pinned one-CPU diagnostic':'Pinned low-address memory-window diagnostic',
    "NEW='c07fa1ff67b73f637d7213599f1e9b727c5ec3a6b9bc7b5dca718bdbbf0c9cbd'":"NEW="+repr(sha(bundle)),
    'single-cpu-trial':'k5-low-window-3g',
    '14875648':'14876672',
    '59c8dc5ec6be26ba190774e15992af39c249b400353d4c567ef462694f7e3205':sha(dtb),
    "assert manifest['bootargs_after']==manifest['bootargs_before']+' maxcpus=1'":"assert manifest['ram_before_bytes']==1<<32 and manifest['ram_after_bytes']==3<<30\nassert manifest['only_changed_dt_property']=='/memory@40000000/reg'",
    'singlecpu-new':'lowwindow-new',
    '165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a':'4a6681c64fc6b173eedf6d3e28062be9596d6ea0c6c1a54b391cdb18a3fce9a9',
    'SINGLE_CPU':'LOW_WINDOW',
    'tzx-single-cpu-':'tzx-low-window-'
}
for before_text,after_text in replacements.items():
    assert before_text in installer, before_text
    installer = installer.replace(before_text,after_text)
compile(installer,'install_k5_low_window.py','exec')
(root/'firmware/install_k5_low_window.py').write_text(installer,encoding='utf8',newline='\n')
print('K5_LOW_WINDOW_PREPARED',json.dumps(manifest),flush=True)
