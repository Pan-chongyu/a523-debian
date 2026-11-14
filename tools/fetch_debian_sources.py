#!/usr/bin/env python3
"""Acquire exact Debian source files with archive-provided SHA256 verification."""
import argparse,concurrent.futures,hashlib,json,lzma,subprocess,time
from pathlib import Path

INDEXES=(('https://deb.debian.org/debian','trixie'),
         ('https://deb.debian.org/debian','trixie-updates'),
         ('https://security.debian.org/debian-security','trixie-security'))

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def download(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.part')
    subprocess.run(['curl','--fail','--location','--silent','--show-error','--retry','3',
        '--connect-timeout','20','--max-time','1800','--continue-at','-',url,'-o',str(temporary)],check=True)
    temporary.replace(path)

def paragraphs(text):
    for entry in text.split('\n\n'):
        fields={};key=None
        for line in entry.splitlines():
            if line.startswith(' ') and key:fields[key]+='\n'+line
            elif ':' in line:key,value=line.split(':',1);fields[key]=value.lstrip()
        if fields:yield fields

def main():
    p=argparse.ArgumentParser();p.add_argument('inventory',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--workers',type=int,default=4);args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    requested=set()
    for line in args.inventory.read_text().splitlines():
        binary,bver,source,sver=line.split('\t');requested.add((source or binary.split(':')[0],sver or bver))
    available={}
    for base,suite in INDEXES:
        for component in ('main','contrib','non-free','non-free-firmware'):
            path=out/'.indexes'/('/'.join((base.split('/')[-1],suite,component)).replace('/','-')+'.xz')
            if not path.exists():download(f'{base}/dists/{suite}/{component}/source/Sources.xz',path)
            for fields in paragraphs(lzma.decompress(path.read_bytes()).decode()):
                key=(fields.get('Package'),fields.get('Version'))
                if key in requested:available[key]=(base,fields)
    def fetch(key):
        if key not in available:return dict(package=key[0],version=key[1],status='missing-index-version')
        base,fields=available[key];items=[];folder=out/'packages'/key[0]/key[1].replace(':','_')
        for line in fields['Checksums-Sha256'].splitlines():
            if not line.strip():continue
            checksum,size,name=line.split();assert Path(name).name==name
            path=folder/name
            if not path.exists() or path.stat().st_size!=int(size) or digest(path)!=checksum:
                download(base+'/'+fields['Directory']+'/'+name,path)
            assert path.stat().st_size==int(size) and digest(path)==checksum,path
            items.append(dict(name=name,bytes=int(size),sha256=checksum))
        return dict(package=key[0],version=key[1],status='verified',files=items)
    report=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(fetch,key):key for key in sorted(requested)}
        for future in concurrent.futures.as_completed(futures):
            key=futures[future]
            try:entry=future.result()
            except Exception as error:entry=dict(package=key[0],version=key[1],status='error',error=str(error))
            report.append(entry);(out/'source-acquisition.json').write_text(json.dumps(report,indent=2)+'\n')
            if len(report)%20==0 or entry['status']!='verified':print('DEBIAN_SOURCES',len(report),len(requested),entry['package'],entry['status'],flush=True)
    bad=[x for x in report if x['status']!='verified']
    print('DEBIAN_SOURCE_ACQUISITION_DONE',len(report),'missing',len(bad),flush=True)
    if bad:raise SystemExit(1)

if __name__=='__main__':main()
