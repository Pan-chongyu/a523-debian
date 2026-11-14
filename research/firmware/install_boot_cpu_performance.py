"""Install/verify/restore the SRAM CPU boost with complete raw-boot readback."""
import hashlib,json,os,struct,subprocess,sys,tarfile
from pathlib import Path
assert os.geteuid()==0 and len(sys.argv)==3
operation,pin=sys.argv[1:];assert operation in ('install','verify','restore') and len(pin)==64
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
OLD='1c2ce9324aae67cf5747c36249db0785c74d52c4094e4e735e37217f60800b41'
BACKUP=Path('/root/tzx-recovery/boot-cpu-performance-v1')
FOLDER=Path('/home/debian/boot-cpu-performance')
STATE=Path('/var/lib/tzx/boot-cpu-performance-installed.json')
PANEL=Path('/var/lib/tzx/boot-panel-installed.json')
sha=lambda data:hashlib.sha256(data).hexdigest()
def run(*cmd):return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT,timeout=60)
def atomic(path,data,mode=0o600):
    path=Path(path);assert not path.is_symlink();path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.boot-cpu-new')
    with temp.open('wb') as stream:
        stream.write(data);os.fchmod(stream.fileno(),mode);stream.flush();os.fsync(stream.fileno())
    temp.replace(path)
def invariant(fd):
    out={}
    for name,lba,size,expected in (
        ('primary-GPT',0,34*512,'82f7b6c741b4292fcb22a2860849e47f811fd85511b7af6b5d2e95faf92f9a40'),
        ('secondary-GPT',244318208-33,33*512,'0289ce6fc405e4b78e755aa5d3df017bf620f65a00c48b86ea7b6227acae8967'),
        ('header',4096,512,'1e07c2743da3e94c0e6f498b4c7a5203c9f7666e3c66b819f64633eb8742ddbb'),
        ('active',98304,15008768,'c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'),
        ('fallback',65536,15008768,'091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3')):
        data=os.pread(fd,size,lba*512);assert len(data)==size and sha(data)==expected,name
        out[name]=sha(data)
    return out
if not FOLDER.exists():
    assert operation=='install'
    allowed={'loader.toc0','loader.toc0.json','guard-files.json','dram-runtime.py','rtc-runtime.py','pmic-runtime.py'}
    with tarfile.open('/home/debian/boot-cpu-performance-stage.tar.gz') as archive:
        members=archive.getmembers();assert len(members)==len(allowed) and {m.name for m in members}==allowed and all(m.isfile() for m in members)
        FOLDER.mkdir()
        for name in allowed:atomic(FOLDER/name,archive.extractfile(name).read(),0o644)
candidate=(FOLDER/'loader.toc0').read_bytes();manifest=json.loads((FOLDER/'loader.toc0.json').read_text())
assert sha(candidate)==pin==manifest['image_sha256'] and len(candidate)==49152
assert manifest['previous_toc0_sha256']==OLD and manifest['ARM_emulation_verified'] and len(manifest['emulation'])==16
assert all(test['status']=='PASS' for test in manifest['emulation'])
assert sha(candidate[0xf80:0xf80+manifest['firmware_bytes']])==manifest['firmware_sha256']
cert=candidate[0xc80:0xf80];n=int.from_bytes(cert[178:434],'big');e=int.from_bytes(cert[436:439],'big')
assert e==65537 and pow(int.from_bytes(cert[-256:],'big'),e,n)==int.from_bytes(hashlib.sha256(cert[4:487]).digest(),'big')
assert cert[445:477].hex()==manifest['firmware_sha256']
check=bytearray(candidate);checksum=struct.unpack_from('<I',check,12)[0];struct.pack_into('<I',check,12,0x5f0a6c39)
assert sum(struct.unpack('<12288I',check))&0xffffffff==checksum
fd=os.open('/dev/mmcblk0',os.O_RDONLY if operation=='verify' else os.O_RDWR|os.O_SYNC)
try:
    invariants=invariant(fd);current=os.pread(fd,49152,256*512)
    if operation!='install':
        record=json.loads(STATE.read_text());assert record['state']=='installed' and current==candidate
        assert record['raw_invariants']==invariants
        for name,item in record['files'].items():
            if name==str(PANEL):
                panel=json.loads(PANEL.read_text());assert panel['toc0_sha256']==pin
                assert panel['installer']=='/home/debian/install_boot_cpu_performance.py'
                for target,entry in panel['files'].items():assert sha(Path(target).read_bytes())==entry['installed_sha256'],target
            else:assert sha(Path(name).read_bytes())==item['installed_sha256'],name
        if operation=='verify':print('BOOT_CPU_PERFORMANCE_FULL_IMAGE_GUARDS_AND_RAW_INVARIANTS_PASS',pin,flush=True)
        else:
            original=(BACKUP/'original-49152.bin').read_bytes();assert sha(original)==OLD
            assert os.pwrite(fd,original,256*512)==49152;os.fsync(fd);assert os.pread(fd,49152,256*512)==original
            for name,item in record['files'].items():
                original=(BACKUP/'files'/name.lstrip('/')).read_bytes();assert sha(original)==item['original_sha256']
                atomic(name,original,item['mode'])
            record['state']='restored';atomic(STATE,(json.dumps(record,indent=2)+'\n').encode())
            os.sync();print('BOOT_CPU_PERFORMANCE_EXACT_ORIGINAL_2SECOND_PANEL_IMAGE_RESTORED',flush=True)
        raise SystemExit(0)
    assert sha(current)==OLD and not BACKUP.exists() and not STATE.exists()
    print(run('python3','/home/debian/install_boot_panel_v2.py','verify',OLD),end='',flush=True)
    proof=json.loads(Path('/var/lib/tzx/boot-latency-qualified.json').read_text())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert proof['status']=='PASS' and proof['boot_id']==boot and proof['toc0_sha256']==OLD
    old_firmware=current[0xf80:0xf80+41280];expected=bytearray(old_firmware)
    for patch in manifest['patches']:
        offset=patch['address']-0x44000;assert struct.unpack_from('<I',expected,offset)[0]==patch['old']
        struct.pack_into('<I',expected,offset,patch['new'])
    assert candidate[0xf80:0xf80+41280]==expected
    replacements={}
    for name,item in json.loads((FOLDER/'guard-files.json').read_text()).items():
        assert sha(Path(name).read_bytes())==item['original_sha256'],name
        data=(FOLDER/item['staged_name']).read_bytes();assert sha(data)==item['candidate_sha256']
        compile(data,name,'exec');replacements[name]=data
    pmic=Path('/var/lib/tzx/pmic-poweroff-installed.json');value=json.loads(pmic.read_text())
    name='/usr/local/lib/tzx-pmic-poweroff/runtime.py'
    assert value['files'][name.lstrip('/')]==sha(Path(name).read_bytes())
    value['files'][name.lstrip('/')]=sha(replacements[name]);value['accepted_toc0_sha256'].append(pin)
    replacements[str(pmic)]=(json.dumps(value,indent=2)+'\n').encode()
    panel=json.loads(PANEL.read_text());assert panel['toc0_sha256']==OLD
    for name,item in panel['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    for name,data in replacements.items():
        if name in panel['files']:panel['files'][name]['installed_sha256']=sha(data)
    panel.update(toc0_sha256=pin,installer='/home/debian/install_boot_cpu_performance.py',
        state='SRAM-performance-installed-pending-actual-reboot',installed_boot_id=boot,
        SRAM_performance_wrapper=True,prior_panel_v2_image_sha256=OLD)
    replacements[str(PANEL)]=(json.dumps(panel,indent=2)+'\n').encode()
    BACKUP.mkdir(mode=0o700);atomic(BACKUP/'original-49152.bin',current)
    files={}
    for name,data in replacements.items():
        path=Path(name);original=path.read_bytes();mode=path.stat().st_mode&0o777
        atomic(BACKUP/'files'/name.lstrip('/'),original,mode)
        files[name]=dict(original_sha256=sha(original),installed_sha256=sha(data),mode=mode)
    try:
        for name,data in replacements.items():atomic(name,data,files[name]['mode'])
        assert os.pwrite(fd,candidate,256*512)==49152;os.fsync(fd)
        assert os.pread(fd,49152,256*512)==candidate and invariant(fd)==invariants
        print(run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'),end='',flush=True)
        print(run('python3','/usr/local/lib/tzx-pmic-poweroff/runtime.py','verify'),end='',flush=True)
        record=dict(state='installed',installed_boot_id=boot,toc0_sha256=pin,previous_toc0_sha256=OLD,
            raw_invariants=invariants,files=files,backup=str(BACKUP),ARM_emulation_verified=True,
            actual_boot_verification='pending',qualified_CPUA_1416MHz_1150mV=True,restore_before_TFA_and_failure=True)
        atomic(STATE,(json.dumps(record,indent=2)+'\n').encode());os.sync()
    except BaseException:
        os.pwrite(fd,current,256*512);os.fsync(fd)
        for name,item in files.items():atomic(name,(BACKUP/'files'/name.lstrip('/')).read_bytes(),item['mode'])
        raise
    print('SRAM_CPU_PERFORMANCE_IMAGE_INSTALLED_AND_READ_BACK',pin,flush=True)
finally:os.close(fd)
