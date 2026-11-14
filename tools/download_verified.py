#!/usr/bin/env python3
"""Bounded parallel HTTP ranges, followed by a complete SHA256 check."""
import concurrent.futures,hashlib,subprocess
from pathlib import Path

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def ranged_download(item,path,workers=4):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size==item['bytes'] and digest(path)==item['sha256']:return path
    size=item['bytes'];block=4*1024*1024;parts=path.with_name(path.name+'.ranges');parts.mkdir(exist_ok=True)
    def get(index):
        start=index*block;end=min(size,start+block)-1;expected=end-start+1
        target=parts/('%05d'%index)
        if target.exists() and target.stat().st_size==expected:return target
        temporary=target.with_suffix('.part');headers=target.with_suffix('.headers')
        for attempt in range(3):
            result=subprocess.run(['curl','--fail','--location','--silent','--show-error','--connect-timeout','20',
                '--max-time','90','--range',str(start)+'-'+str(end),'--max-filesize',str(expected),
                '--dump-header',str(headers),'--output',str(temporary),item['url']],capture_output=True)
            if result.returncode==0 and temporary.exists() and temporary.stat().st_size==expected:
                text=headers.read_text(errors='ignore').lower()
                assert ('content-range: bytes %d-%d/%d'%(start,end,size)) in text,'Server ignored the requested byte range'
                temporary.replace(target);headers.unlink(missing_ok=True);return target
        raise RuntimeError('Range download failed: '+item['name']+' '+str(index))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        paths=list(pool.map(get,range((size+block-1)//block)))
    temp=path.with_name(path.name+'.assembling')
    with temp.open('wb') as output:
        for part in paths:
            with part.open('rb') as source:
                for data in iter(lambda:source.read(1024*1024),b''):output.write(data)
    assert temp.stat().st_size==size and digest(temp)==item['sha256'],'Complete source SHA256 failed'
    temp.replace(path)
    for part in paths:part.unlink()
    parts.rmdir()
    return path
