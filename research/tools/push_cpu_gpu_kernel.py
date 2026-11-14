"""Upload the pinned kernel in bounded chunks over the tablet's USB network."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
r=Path(__file__).resolve().parents[1]
s=r/'build/cpu-gpu-kernel'
helper=[sys.executable,'-X','utf8',str(r/'tools/tablet_ssh.py')]
subprocess.run(helper+['--root','--command','install -d -o debian -g debian /home/debian/cpu-gpu-kernel /home/debian/cpu-gpu-kernel/upload-parts'],check=True)
data=(s/'linux-bundle.bin').read_bytes()
assert hashlib.sha256(data).hexdigest()==json.loads((s/'linux-bundle.json').read_text())['sha256']
parts=s/'upload-parts';parts.mkdir(exist_ok=True)
records=[]
for i,off in enumerate(range(0,len(data),1024*1024)):
    p=parts/(f'{i:03d}.part');chunk=data[off:off+1024*1024];p.write_bytes(chunk)
    for attempt in range(4):
        result=subprocess.run(['scp','-q','-l','4000','-i',str(r/'private/tzx-host-ed25519'),
            '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
            '-o','UserKnownHostsFile='+str(r/'private/tablet_known_hosts'),str(p),
            'debian@192.168.77.2:/home/debian/cpu-gpu-kernel/upload-parts/'+p.name],capture_output=True,timeout=40)
        if not result.returncode:break
        print('UPLOAD_RETRY',i,attempt+1,flush=True);time.sleep(1)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    records.append(dict(name=p.name,sha256=hashlib.sha256(chunk).hexdigest(),bytes=len(chunk)))
    if i%4==0:print('UPLOADED_PARTS',i+1,flush=True)
manifest=dict(chunks=records,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
(s/'upload-parts.json').write_text(json.dumps(manifest,indent=2)+'\n')
for p in [s/'linux-bundle.json',s/'kernel.config',s/'panfrost.ko',s/'upload-parts.json',r/'firmware/install_cpu_gpu_kernel.py']:
    subprocess.run(helper+['--file',str(p),'--remote','/home/debian/cpu-gpu-kernel/'+p.name,'--timeout','45'],check=True)
command='''python3 - <<'PY'
import hashlib,json
from pathlib import Path
r=Path('/home/debian/cpu-gpu-kernel');m=json.loads((r/'upload-parts.json').read_text());data=bytearray()
for i,c in enumerate(m['chunks']):
 assert c['name']==f'{i:03d}.part'
 b=(r/'upload-parts'/c['name']).read_bytes();assert len(b)==c['bytes'] and hashlib.sha256(b).hexdigest()==c['sha256'];data.extend(b)
assert len(data)==m['bytes'] and hashlib.sha256(data).hexdigest()==m['sha256']
(r/'linux-bundle.bin').write_bytes(data)
print('ALL_KERNEL_UPLOAD_CHUNKS_AND_BUNDLE_VERIFIED',m['sha256'])
PY'''
subprocess.run(helper+['--command',command,'--output','cpu-gpu-kernel-upload-verified.txt','--timeout','60'],check=True)
print('CPU_GPU_KERNEL_UPLOAD_COMPLETE',flush=True)
