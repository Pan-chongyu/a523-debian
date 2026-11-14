"""Install or restore the exact pre-DRAM panel image and its scoped handoff."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile

assert os.geteuid()==0 and len(sys.argv)==3
operation,pin=sys.argv[1:]
assert operation in ('install','verify','restore') and len(pin)==64
assert os.uname().release=='7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip()=='244318208'
OLD='50537c7ff9d9b20461c0a1181f3b4f04240e63be7aece9f49ba1ce6c18bc0c9b'
FOLDER=Path('/home/debian/boot-panel-early')
BACKUP=Path('/root/tzx-recovery/boot-panel-early-v1')
STATE=Path('/var/lib/tzx/boot-panel-installed.json')
BOOT=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
sha=lambda b:hashlib.sha256(b).hexdigest()

def atomic(path,data,mode=0o600):
    path=Path(path)
    assert not path.is_symlink()
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.boot-panel-new')
    with temp.open('wb') as stream:
        stream.write(data);os.fchmod(stream.fileno(),mode);stream.flush();os.fsync(stream.fileno())
    temp.replace(path)
    fd=os.open(path.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)

def record(path,value):atomic(path,(json.dumps(value,indent=2)+'\n').encode())
def run(*args,timeout=45):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout)
def invariant(fd):
    out={}
    for name,lba,size,expected in (
        ('primary-GPT',0,34*512,'82f7b6c741b4292fcb22a2860849e47f811fd85511b7af6b5d2e95faf92f9a40'),
        ('secondary-GPT',244318208-33,33*512,'0289ce6fc405e4b78e755aa5d3df017bf620f65a00c48b86ea7b6227acae8967'),
        ('header',4096,512,'1e07c2743da3e94c0e6f498b4c7a5203c9f7666e3c66b819f64633eb8742ddbb'),
        ('active',98304,15008768,'c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'),
        ('fallback',65536,15008768,'091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3')):
        data=os.pread(fd,size,lba*512)
        assert len(data)==size and sha(data)==expected,name
        out[name]=sha(data)
    return out

if not FOLDER.exists():
    assert operation=='install'
    allowed={'loader.toc0','loader.toc0.json','guard-files.json',
        'tzx-dram-gpu-runtime.py','tzx-rtc-context-runtime.py','tzx-pmic-poweroff-runtime.py'}
    with tarfile.open('/home/debian/boot-panel-stage.tar.gz') as archive:
        assert {m.name for m in archive.getmembers()}==allowed
        assert len(archive.getmembers())==len(allowed) and all(m.isfile() for m in archive.getmembers())
        FOLDER.mkdir(mode=0o755)
        for name in sorted(allowed):atomic(FOLDER/name,archive.extractfile(name).read(),0o644)
candidate=(FOLDER/'loader.toc0').read_bytes()
manifest=json.loads((FOLDER/'loader.toc0.json').read_text())
guards=json.loads((FOLDER/'guard-files.json').read_text())
assert len(candidate)==manifest['image_bytes']==49152 and sha(candidate)==manifest['image_sha256']==pin
assert manifest['ARM_emulation_verified'] and len(manifest['emulation'])==13
assert all(t['status']=='PASS' for t in manifest['emulation'])
assert manifest['previous_toc0_sha256']==OLD and guards['toc0_sha256']==pin
assert manifest['before_DRAM_training'] and manifest['original_voltage_hook_called_first']
assert manifest['firmware_bytes']==40896 and manifest['hook_bytes']==4004
assert sha(candidate[0xf80:0xf80+40896])==manifest['firmware_sha256']
assert candidate[0xf80+40896:]==bytes(49152-0xf80-40896)
assert struct.unpack_from('<I',candidate,0x64)[0]==0x44000
cert=candidate[0xc80:0xf80]
n=int.from_bytes(cert[178:434],'big');e=int.from_bytes(cert[436:439],'big')
assert e==65537 and pow(int.from_bytes(cert[-256:],'big'),e,n)==int.from_bytes(hashlib.sha256(cert[4:487]).digest(),'big')
assert cert[445:477].hex()==manifest['firmware_sha256']
check=bytearray(candidate);expected=struct.unpack_from('<I',check,12)[0]
struct.pack_into('<I',check,12,0x5f0a6c39)
assert sum(struct.unpack('<12288I',check))&0xffffffff==expected
fd=os.open('/dev/mmcblk0',os.O_RDONLY if operation=='verify' else os.O_RDWR|os.O_SYNC)
try:
    before=invariant(fd)
    current=os.pread(fd,49152,256*512)
    if operation!='install':
        value=json.loads(STATE.read_text())
        assert value['toc0_sha256']==pin and current==candidate
        assert value['raw_invariants']==before
        for name,item in value['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
        if operation=='verify':
            print('EARLY_PANEL_FULL_TOC0_AND_HANDOFF_FILES_VERIFIED',pin,flush=True)
        else:
            original=(BACKUP/'original-49152.bin').read_bytes()
            assert len(original)==49152 and sha(original[:40960])==OLD
            assert os.pwrite(fd,original,256*512)==49152;os.fsync(fd)
            assert os.pread(fd,49152,256*512)==original
            for name,item in value['files'].items():
                if item['original_sha256'] is None:Path(name).unlink()
                else:
                    data=(BACKUP/'files'/name.lstrip('/')).read_bytes()
                    assert sha(data)==item['original_sha256']
                    atomic(name,data,item['mode'])
            run('systemctl','daemon-reload')
            value.update(state='exact-original-boot-and-startup-files-restored',restored_boot_id=BOOT)
            record(STATE,value)
            print('EARLY_PANEL_EXACT_ORIGINAL_25_SECOND_VERSION_RESTORED',flush=True)
        raise SystemExit(0)
    assert not BACKUP.exists() and not STATE.exists() and sha(current[:40960])==OLD
    assert not run('systemctl','--failed','--plain','--no-legend').strip()
    proof=json.loads(Path('/var/lib/tzx/screen-fast-final-qualified.json').read_text())
    assert proof['boot_id']==BOOT and proof['status']=='PASS' and proof['poweroff_key_on_verified']
    assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
    expected=bytearray(current[0xf80:0xf80+36508])
    for patch in manifest['patches']:
        off=patch['address']-0x44000
        assert struct.unpack_from('<I',expected,off)[0]==patch['old']
        struct.pack_into('<I',expected,off,patch['new'])
    assert len(manifest['patches'])==1 and candidate[0xf80:0xf80+36508]==expected
    originals={};replacements={};modes={}
    for name,item in guards['guard_files'].items():
        original=Path(name).read_bytes();data=(FOLDER/item['staged_name']).read_bytes()
        assert sha(original)==item['original_sha256'] and sha(data)==item['candidate_sha256'],name
        compile(data,name,'exec')
        originals[name]=original;replacements[name]=data
    name='/var/lib/tzx/pmic-poweroff-installed.json'
    originals[name]=Path(name).read_bytes();value=json.loads(originals[name])
    runtime='/usr/local/lib/tzx-pmic-poweroff/runtime.py'
    assert value['files'][runtime.lstrip('/')]==sha(originals[runtime])
    assert OLD in value['accepted_toc0_sha256'] and pin not in value['accepted_toc0_sha256']
    value['files'][runtime.lstrip('/')]=sha(replacements[runtime])
    value['accepted_toc0_sha256'].append(pin)
    value['early_panel_boot_id']=BOOT
    replacements[name]=(json.dumps(value,indent=2)+'\n').encode()
    replacements['/usr/local/lib/tzx-boot-panel/handoff.py']=Path('/home/debian/boot_panel_handoff.py').read_bytes()
    replacements['/etc/systemd/system/tzx-boot-panel-handoff.service']=(
        '[Unit]\nDescription=Release SRAM early panel before native drivers\nDefaultDependencies=no\n'
        'After=systemd-remount-fs.service tzx-cpub.service systemd-udev-trigger.service\n'
        'Before=tzx-touch.service shutdown.target\nConflicts=shutdown.target\n'
        '[Service]\nType=oneshot\nRemainAfterExit=yes\nTimeoutStartSec=20s\n'
        'ExecStart=/usr/bin/python3 /usr/local/lib/tzx-boot-panel/handoff.py\n').encode()
    replacements['/etc/systemd/system/tzx-touch.service.d/99-sram-panel-handoff.conf']=(
        '[Unit]\nRequires=tzx-boot-panel-handoff.service\nAfter=tzx-boot-panel-handoff.service\n').encode()
    for name in set(replacements)-set(originals):assert not Path(name).exists(),name
    BACKUP.mkdir(parents=True)
    atomic(BACKUP/'original-49152.bin',current)
    atomic(BACKUP/'install_boot_panel.py',Path(__file__).read_bytes())
    record(BACKUP/'known-good-screen-proof.json',proof)
    files={}
    for name,data in replacements.items():
        mode=Path(name).stat().st_mode&0o777 if name in originals else 0o644
        if name in originals:atomic(BACKUP/'files'/name.lstrip('/'),originals[name],mode)
        files[name]=dict(original_sha256=sha(originals[name]) if name in originals else None,
            installed_sha256=sha(data),mode=mode)
    record(BACKUP/'before.json',dict(boot_id=BOOT,files=files,raw_invariants=before))
    try:
        for name,data in replacements.items():atomic(name,data,files[name]['mode'])
        run('systemd-analyze','verify','--man=no','tzx-touch.service','tzx-boot-panel-handoff.service','graphical.target')
        run('systemctl','daemon-reload')
        os.sync()
        assert os.pwrite(fd,candidate,256*512)==49152;os.fsync(fd)
        assert os.pread(fd,49152,256*512)==candidate and invariant(fd)==before
        print(run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'),end='',flush=True)
        print(run('python3','/usr/local/lib/tzx-pmic-poweroff/runtime.py','verify'),end='',flush=True)
        record(STATE,dict(state='installed-pending-real-early-screen-boot',installed_boot_id=BOOT,
            toc0_sha256=pin,toc0_bytes=49152,original_toc0_sha256=OLD,files=files,backup=str(BACKUP),
            raw_invariants=before,ARM_emulation_verified=True,PMIC_voltage_values_unchanged=True,
            early_panel_qualification=False,user_first_light_confirmation='pending'))
        os.sync()
    except BaseException:
        assert os.pwrite(fd,current,256*512)==49152;os.fsync(fd)
        assert os.pread(fd,49152,256*512)==current
        for name in replacements:
            if name in originals:atomic(name,originals[name],files[name]['mode'])
            else:Path(name).unlink(missing_ok=True)
        run('systemctl','daemon-reload')
        raise
    print('EARLY_PANEL_49152_BYTE_IMAGE_AND_NATIVE_HANDOFF_INSTALLED',pin,flush=True)
finally:os.close(fd)
