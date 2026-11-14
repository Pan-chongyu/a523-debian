"""Check that the isolation tree changes no unrelated base DT properties."""
import json,struct
from fel_device import ROOT

def props(data):
    assert data[:4]==bytes.fromhex('d00dfeed')
    pos,strings=struct.unpack_from('>II',data,8)
    stack=[];result={}
    while True:
        token=struct.unpack_from('>I',data,pos)[0];pos+=4
        if token==1:
            end=data.index(0,pos);stack.append(data[pos:end].decode())
            pos=(end+4)&~3
        elif token==2:stack.pop()
        elif token==3:
            size,nameoff=struct.unpack_from('>II',data,pos);pos+=8
            start=strings+nameoff;end=data.index(0,start)
            key=('/'+'/'.join(stack[1:]),data[start:end].decode())
            result[key]=data[pos:pos+size];pos=(pos+size+3)&~3
        elif token==4:pass
        elif token==9:return result
        else:raise AssertionError(token)

base=(ROOT/'build/known-good-base-3/board.dtb').read_bytes()
touch=(ROOT/'build/board-touch-only.dtb').read_bytes()
a,b=props(base),props(touch)
changed=[]
for key in sorted(a.keys()|b.keys()):
    if a.get(key)==b.get(key):continue
    path,name=key
    allowed=path.startswith('/touch-i2c') or path=='/regulator-touch-vcc' or key in {
        ('/aliases','i2c1'),('/soc/pinctrl@2000000','phandle'),
        ('/soc/pinctrl@2000000','vcc-ph-supply')}
    assert allowed,('Unexpected changed property',key)
    assert key not in a,('Unexpected replacement of an existing property',key)
    changed.append({'node':path,'property':name})
assert b[('/touch-i2c/touchscreen@40','compatible')]==b'tzx,p30-gsl3670-candidate\0'
assert b[('/chosen','linux,initrd-end')]==a[('/chosen','linux,initrd-end')]
original=(ROOT/'build/linux-bundle.bin').read_bytes()
for directory,expected in [('recovery-new-image-old-dtb-slot',base),('touch-only-slot',touch)]:
    candidate=(ROOT/'build'/directory/'linux-bundle.bin').read_bytes()
    manifest=json.loads((ROOT/'build'/directory/'linux-bundle.json').read_text())
    dt=manifest['items'][1];off=(dt['lba']-4096)*512;end=off+((dt['bytes']+511)&~511)
    assert len(candidate)==len(original)
    assert candidate[off:off+len(expected)]==expected
    assert not any(candidate[off+len(expected):end])
    assert candidate[20:68]==original[20:68]
    assert candidate[72:off]==original[72:off]
    assert candidate[end:]==original[end:]
    assert candidate[:16]==original[:16]
report={'result':'PASS','base_existing_properties_preserved':len(a),
        'touch_properties_added':changed,
        'recovery_fdt_identical_to_base':True,
        'both_bundles_only_change_header_crcs_and_dtb_slot':True,
        'hardware_tested':False}
text=json.dumps(report,indent=2)
(ROOT/'evidence/touch-only-dtb-isolation-check.json').write_text(text,encoding='utf8')
print(text)
