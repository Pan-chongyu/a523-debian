"""Compare allocatable ELF sections, excluding the reproducible build ID."""
import hashlib
import json
from pathlib import Path
import struct

def sections(path, normalize_paths=False):
    data=Path(path).read_bytes()
    assert data[:6]==b'\x7fELF\x02\x01'
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
    offset,entsize,count,strings=header[6],header[11],header[12],header[13]
    entries=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*entsize) for i in range(count)]
    names=data[entries[strings][4]:entries[strings][4]+entries[strings][5]]
    result={}
    for entry in entries:
        name=names[entry[0]:].split(b'\0',1)[0].decode()
        if entry[2]&2 and name!='.note.gnu.build-id':
            payload=data[entry[4]:entry[4]+entry[5]] if entry[1]!=8 else b''
            if normalize_paths:
                payload=payload.replace(b'/opt/a523-debian-20261109/linux-extended-source/',
                                        b'/opt/a523-debian-20261109/linux-7.3.3/')
            result[name]=dict(size=len(payload) if entry[1]!=8 else entry[5],type=entry[1],flags=entry[2],
                             sha256=hashlib.sha256(payload).hexdigest())
    return result

def compare(before,after):
    a,b=sections(before),sections(after)
    changes={name:dict(before=a.get(name),after=b.get(name)) for name in a.keys()|b.keys() if a.get(name)!=b.get(name)}
    normalized_equal=sections(before,True)==sections(after,True)
    return dict(before=str(before),after=str(after),allocatable_sections_equal=not changes,
                equal_after_normalizing_source_directory=normalized_equal,changes=changes)

if __name__=='__main__':
    import sys
    before,after,output=map(Path,sys.argv[1:])
    records=[]
    for path in before.rglob('*.ko'):
        candidate=after/path.relative_to(before)
        if candidate.exists(): records.append(compare(path,candidate))
    output.write_text(json.dumps(records,indent=2)+'\n')
    print('MODULE_CODE_AUDIT',len(records),'changed',sum(not r['allocatable_sections_equal'] for r in records))
    for record in records:
        if not record['allocatable_sections_equal']: print(record['before'],list(record['changes']))
