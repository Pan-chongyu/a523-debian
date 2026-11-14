"""Package isolated modules and boot-conditional diagnostic service overrides."""
import hashlib,json,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'build/va48-kernel'
stage=folder/'minimal-runtime'
assert not stage.exists()
build=json.loads((folder/'BUILD_COMPLETE.json').read_text())
release='7.3.3-tzx-a523-va48';assert build['release']==release
files={}
module_root=folder/'modules/lib/modules'/release
for path in module_root.rglob('*'):
    if path.name in ('build','source'):
        continue
    if path.is_file() and not path.is_symlink():
        files['lib/modules/'+release+'/'+path.relative_to(module_root).as_posix()]=path.read_bytes()
module=(folder/'rtc-module/tzx_rtc_log.ko').read_bytes()
module_sha=hashlib.sha256(module).hexdigest()
assert module_sha==build['files']['rtc-module/tzx_rtc_log.ko']
assert release.encode()+b' ' in module
files['usr/local/lib/tzx-va48/rtc/tzx_rtc_log.ko']=module
runtime=(root/'firmware/tzx_rtc_log_runtime.py').read_text()
assert runtime.count('7.3.3-tzx-a523-accel1')==1
assert runtime.count('80e8e0522faec7ead866a254667a3272ccd6939551ed2f13bce0f2aa1b3fca73')==1
runtime=runtime.replace('7.3.3-tzx-a523-accel1',release).replace('80e8e0522faec7ead866a254667a3272ccd6939551ed2f13bce0f2aa1b3fca73',module_sha)
files['usr/local/lib/tzx-va48/rtc/runtime.py']=runtime.encode()
files['boot/config-'+release]=(folder/'kernel.config').read_bytes()
files['usr/lib/systemd/system-generators/tzx-va48-diagnostic']=(root/'firmware/tzx_va48_generator.py').read_bytes()
generator=files['usr/lib/systemd/system-generators/tzx-va48-diagnostic'].decode()
compile(generator,'tzx-va48-diagnostic','exec')
for name,data in files.items():
    path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    path.chmod(0o755 if 'system-generators/' in name else 0o644)
manifest={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}
(stage/'FILES.json').write_text(json.dumps(manifest,indent=2)+'\n')
archive=folder/'minimal-runtime.tar.gz'
with tarfile.open(archive,'w:gz') as stream:
    for name in [*sorted(files),'FILES.json']:
        stream.add(stage/name,arcname=name,recursive=False)
record={'files':len(files),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'bytes':archive.stat().st_size,'boot_conditioned':True,'board_drivers_disabled_for_diagnostic':True}
(folder/'MINIMAL_RUNTIME.json').write_text(json.dumps(record,indent=2)+'\n')
print('VA48_MINIMAL_RUNTIME_PACKAGED',json.dumps(record))
