"""Extend the three exact boot hash guards; preserve every existing check."""
import hashlib,json,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];folder=root/'build/boot-cpu-performance'
manifest=json.loads((folder/'loader.toc0.json').read_text());assert manifest['ARM_emulation_verified']
pin=manifest['image_sha256'];old=manifest['previous_toc0_sha256'];files={}
for short,component in (('dram','tzx-dram-gpu'),('rtc','tzx-rtc-context'),('pmic','tzx-pmic-poweroff')):
    original=(root/'build/performance-mode-base'/(short+'-runtime.py')).read_bytes()
    text=original.decode();needle="'"+old+"')";assert text.count(needle)==1
    text=text.replace(needle,"'"+old+"', '"+pin+"')");compile(text,component,'exec')
    target=folder/(short+'-runtime.py');target.write_text(text,encoding='utf-8',newline='\n')
    files['/usr/local/lib/'+component+'/runtime.py']=dict(original_sha256=hashlib.sha256(original).hexdigest(),
        candidate_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),staged_name=target.name)
(folder/'guard-files.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
target=root/'build/boot-cpu-performance-stage.tar.gz';assert not target.exists()
with tarfile.open(target,'w:gz') as archive:
    for name in ('loader.toc0','loader.toc0.json','guard-files.json','dram-runtime.py','rtc-runtime.py','pmic-runtime.py'):archive.add(folder/name,arcname=name)
print('BOOT_CPU_PERFORMANCE_FULL_HASH_GUARDS_PACKAGED',pin,flush=True)
