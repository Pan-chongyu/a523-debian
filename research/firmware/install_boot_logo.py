"""Exact-board transactional splash installation, complete readback and rollback."""
import hashlib,json,os,struct,subprocess,sys,tarfile,zlib
from pathlib import Path
assert os.geteuid()==0 and len(sys.argv)==3
operation,pin=sys.argv[1:];assert operation in ('install','verify','restore') and len(pin)==64
assert os.uname().release=='7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert Path('/sys/class/block/mmcblk0/size').read_text().strip()=='244318208'
OLD='367d51b493c2c647e12cfb24264afcac714cebcaa8b4605301620211f0befa1c'
OLD_BUNDLE='c5d306559886e947d702457a92149e4c2e6c41713188bee6bbbdcc22409f0da7'
OLD_HEADER='1e07c2743da3e94c0e6f498b4c7a5203c9f7666e3c66b819f64633eb8742ddbb'
FOLDER=Path('/home/debian/boot-logo');BACKUP=Path('/root/tzx-recovery/boot-logo-v1')
STATE=Path('/var/lib/tzx/boot-logo-installed.json');PANEL=Path('/var/lib/tzx/boot-panel-installed.json')
sha=lambda b:hashlib.sha256(b).hexdigest()
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=60)
def atomic(path,data,mode=0o600):
    path=Path(path);assert not path.is_symlink();path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.logo-new')
    with temp.open('wb') as f:
        f.write(data);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
    temp.replace(path)
    fd=os.open(path.parent,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def encoded(value):return (json.dumps(value,indent=2)+'\n').encode()
def invariant(fd):
    result={}
    for name,lba,size,expected in (
        ('primary-GPT',0,34*512,'82f7b6c741b4292fcb22a2860849e47f811fd85511b7af6b5d2e95faf92f9a40'),
        ('secondary-GPT',244318208-33,33*512,'0289ce6fc405e4b78e755aa5d3df017bf620f65a00c48b86ea7b6227acae8967'),
        ('fallback',65536,15008768,'091ebfe06aa47ca3a4ac7e347838dd6175c575771032e1703e6b7b1480e460e3')):
        data=os.pread(fd,size,lba*512);assert len(data)==size and sha(data)==expected,name
        result[name]=sha(data)
    return result
def device_tree(data):
    magic,size,off,strings,_,version,last,_,strsize,structsize=struct.unpack_from('>10I',data)
    assert magic==0xd00dfeed and size==len(data) and version==17 and last==16
    stack=[];nodes={};position=off
    while position<off+structsize:
        token=struct.unpack_from('>I',data,position)[0];position+=4
        if token==1:
            end=data.index(0,position);stack.append(data[position:end].decode());position=(end+4)&~3
            nodes['/'.join(stack) or '/']={}
        elif token==2:stack.pop()
        elif token==3:
            length,nameoff=struct.unpack_from('>II',data,position);position+=8
            name=data[strings+nameoff:data.index(0,strings+nameoff)].decode()
            nodes['/'.join(stack) or '/'][name]=data[position:position+length];position=(position+length+3)&~3
        elif token==4:pass
        elif token==9:break
        else:raise AssertionError(token)
    return nodes
if not FOLDER.exists():
    assert operation=='install'
    allowed={'loader.toc0','loader.toc0.json','payload.bin','guard-files.json','dram-runtime.py','rtc-runtime.py',
             'pmic-runtime.py','handoff.py','linux-bundle.json','board.dtb','dtb-sectors.bin','active-header.bin','splash-preview.png'}
    with tarfile.open('/home/debian/boot-logo-stage.tar.gz') as archive:
        members=archive.getmembers();assert len(members)==len(allowed) and {m.name for m in members}==allowed and all(m.isfile() for m in members)
        FOLDER.mkdir()
        for name in allowed:atomic(FOLDER/name,archive.extractfile(name).read(),0o644)
m=json.loads((FOLDER/'loader.toc0.json').read_text());candidate=(FOLDER/'loader.toc0').read_bytes()
payload=(FOLDER/'payload.bin').read_bytes();bundle=json.loads((FOLDER/'linux-bundle.json').read_text())
header=(FOLDER/'active-header.bin').read_bytes();dtb=(FOLDER/'board.dtb').read_bytes();dtb_sectors=(FOLDER/'dtb-sectors.bin').read_bytes()
assert sha(candidate)==pin==m['image_sha256'] and len(candidate)==49152
assert m['ARM_emulation_verified'] and len(m['emulation'])>=16 and all(t['status']=='PASS' for t in m['emulation'])
assert m['previous_toc0_sha256']==OLD and sha(payload)==m['payload_sha256']
assert len(payload)==m['payload_bytes'] and zlib.crc32(payload)==m['payload_crc32'] and m['payload_lba']==49152
assert 49152+len(payload)//512<65536 and len(payload)%512==0
assert sha(candidate[0xf80:0xf80+m['firmware_bytes']])==m['firmware_sha256']
cert=candidate[0xc80:0xf80];n=int.from_bytes(cert[178:434],'big');e=int.from_bytes(cert[436:439],'big')
assert e==65537 and pow(int.from_bytes(cert[-256:],'big'),e,n)==int.from_bytes(hashlib.sha256(cert[4:487]).digest(),'big')
assert cert[445:477].hex()==m['firmware_sha256']
check=bytearray(candidate);checksum=struct.unpack_from('<I',check,12)[0];struct.pack_into('<I',check,12,0x5f0a6c39)
assert sum(struct.unpack('<12288I',check))&0xffffffff==checksum
assert sha(header)==bundle['header_sha256'] and len(header)==512
check=bytearray(header);crc=struct.unpack_from('<I',check,16)[0];struct.pack_into('<I',check,16,0)
assert zlib.crc32(check)==crc and header[:8]==b'A523BND1'
assert bundle['previous_bundle_sha256']==OLD_BUNDLE and bundle['reserved_boot_splash']==[0x42000000,0x900000]
assert bundle['items'][1]['lba']==123194 and bundle['items'][1]['bytes']==len(dtb) and sha(dtb)==bundle['items'][1]['sha256']
assert dtb_sectors==dtb+bytes(20480-len(dtb)) and len(dtb_sectors)==20480
fd=os.open('/dev/mmcblk0',os.O_RDONLY if operation=='verify' else os.O_RDWR|os.O_SYNC)
try:
    invariants=invariant(fd);current=os.pread(fd,49152,256*512)
    if operation!='install':
        record=json.loads(STATE.read_text());assert record['state'] in ('installed','actual-reboot-verified')
        assert current==candidate and record['raw_invariants']==dict(invariants,header=sha(header),active=bundle['sha256'])
        assert os.pread(fd,len(payload),49152*512)==payload
        assert os.pread(fd,512,4096*512)==header and os.pread(fd,512,98304*512)==header
        assert sha(os.pread(fd,15008768,98304*512))==bundle['sha256']
        for name,item in record['files'].items():
            if name==str(PANEL):
                value=json.loads(PANEL.read_text());assert value['toc0_sha256']==pin and value['installer']=='/home/debian/install_boot_logo.py'
                for target,entry in value['files'].items():assert sha(Path(target).read_bytes())==entry['installed_sha256'],target
            else:assert sha(Path(name).read_bytes())==item['installed_sha256'],name
        if operation=='verify':print('BOOT_LOGO_SIGNED_IMAGE_ASSET_FULL_RAW_AND_FILE_READBACK_PASS',pin,flush=True)
        else:
            before=json.loads((BACKUP/'before.json').read_text())
            for name,lba in (('toc0.bin',256),('dtb-sectors.bin',123194),('bundle-header.bin',98304),('active-header.bin',4096),('asset-before.bin',49152)):
                data=(BACKUP/name).read_bytes();assert sha(data)==before['raw'][name]
                assert os.pwrite(fd,data,lba*512)==len(data)
            os.fsync(fd)
            assert sha(os.pread(fd,49152,256*512))==OLD and sha(os.pread(fd,15008768,98304*512))==OLD_BUNDLE
            for name,item in record['files'].items():
                data=(BACKUP/'files'/name.lstrip('/')).read_bytes();assert sha(data)==item['original_sha256']
                atomic(name,data,item['mode'])
            record['state']='restored';atomic(STATE,encoded(record));os.sync()
            print('BOOT_LOGO_EXACT_PERFORMANCE_BOOT_AND_ALL_BEFORE_IMAGES_RESTORED',flush=True)
        raise SystemExit(0)
    assert sha(current)==OLD and not STATE.exists() and not BACKUP.exists()
    assert sha(os.pread(fd,512,4096*512))==OLD_HEADER and sha(os.pread(fd,15008768,98304*512))==OLD_BUNDLE
    print(run('python3','/home/debian/install_boot_cpu_performance.py','verify',OLD),end='',flush=True)
    # Exactly two code patches and an appended bounded loader; all voltage,
    # training, CPU restoration and original payload validation bytes retained.
    expected=bytearray(current[0xf80:0xf80+43168])
    for patch in m['patches']:
        offset=patch['address']-0x44000;assert struct.unpack_from('<I',expected,offset)[0]==patch['old']
        struct.pack_into('<I',expected,offset,patch['new'])
    assert candidate[0xf80:0xf80+43168]==expected and len(m['patches'])==2
    old_dtb=os.pread(fd,20220,123194*512);before_tree=device_tree(old_dtb);after_tree=device_tree(dtb)
    assert after_tree.pop('/reserved-memory/boot-splash@42000000')=={'reg':struct.pack('>4I',0,0x42000000,0,0x900000),'no-map':b''}
    assert before_tree==after_tree, 'Only the explicit splash reservation may change'
    old_bundle=os.pread(fd,15008768,98304*512);proposed=bytearray(old_bundle)
    proposed[:512]=header;offset=(123194-98304)*512;proposed[offset:offset+20480]=dtb_sectors
    assert sha(proposed)==bundle['sha256']
    changes={}
    for name,item in json.loads((FOLDER/'guard-files.json').read_text()).items():
        assert sha(Path(name).read_bytes())==item['original_sha256'],name
        data=(FOLDER/item['staged_name']).read_bytes();assert sha(data)==item['candidate_sha256'];compile(data,name,'exec')
        changes[name]=data
    pmic=Path('/var/lib/tzx/pmic-poweroff-installed.json');value=json.loads(pmic.read_text())
    target='/usr/local/lib/tzx-pmic-poweroff/runtime.py';assert value['files'][target.lstrip('/')]==sha(Path(target).read_bytes())
    value['files'][target.lstrip('/')]=sha(changes[target]);value['accepted_toc0_sha256'].append(pin);changes[str(pmic)]=encoded(value)
    changes['/home/debian/installed-bundle.json']=(FOLDER/'linux-bundle.json').read_bytes()
    emmc_manifest=Path('/usr/local/lib/tzx-emmc-hs/manifest.json')
    emmc=json.loads(emmc_manifest.read_text())
    assert emmc['boot_header_sha256']==OLD_HEADER
    assert emmc['kernel_image_sha256']==bundle['items'][0]['sha256']
    for name,digest in emmc['files'].items():assert sha(Path(name).read_bytes())==digest,name
    emmc['boot_header_sha256']=sha(header)
    changes[str(emmc_manifest)]=encoded(emmc)
    for name in ('/boot/board.dtb','/home/debian/current-bundle/board.dtb'):
        assert Path(name).read_bytes()==old_dtb;changes[name]=dtb
    panel=json.loads(PANEL.read_text());assert panel['toc0_sha256']==OLD
    for name,item in panel['files'].items():assert sha(Path(name).read_bytes())==item['installed_sha256'],name
    for name,data in changes.items():
        if name in panel['files']:panel['files'][name]['installed_sha256']=sha(data)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    raw_pins=dict(invariants,header=sha(header),active=bundle['sha256'])
    panel.update(toc0_sha256=pin,installer='/home/debian/install_boot_logo.py',state='logo-installed-pending-reboot',
        installed_boot_id=boot,raw_invariants=raw_pins,custom_boot_logo=True)
    changes[str(PANEL)]=encoded(panel)
    BACKUP.mkdir(mode=0o700);raw={}
    for name,lba,size in (('toc0.bin',256,49152),('dtb-sectors.bin',123194,20480),('bundle-header.bin',98304,512),
                          ('active-header.bin',4096,512),('asset-before.bin',49152,len(payload))):
        data=os.pread(fd,size,lba*512);assert len(data)==size;atomic(BACKUP/name,data);raw[name]=sha(data)
    files={}
    for name,data in changes.items():
        path=Path(name);original=path.read_bytes();mode=path.stat().st_mode&0o777
        atomic(BACKUP/'files'/name.lstrip('/'),original,mode)
        files[name]=dict(original_sha256=sha(original),installed_sha256=sha(data),mode=mode)
    before=dict(boot_id=boot,raw=raw,files=files);atomic(BACKUP/'before.json',encoded(before))
    try:
        # The asset and harmless reservation are installed before selecting
        # the signed loader. Existing kernel and fallback sectors never move.
        for data,lba in ((payload,49152),(dtb_sectors,123194),(header,98304),(header,4096)):
            assert os.pwrite(fd,data,lba*512)==len(data);os.fsync(fd);assert os.pread(fd,len(data),lba*512)==data
        for name,data in changes.items():atomic(name,data,files[name]['mode'])
        assert os.pwrite(fd,candidate,256*512)==49152;os.fsync(fd)
        assert os.pread(fd,49152,256*512)==candidate and invariant(fd)==invariants
        assert sha(os.pread(fd,15008768,98304*512))==bundle['sha256']
        print(run('python3','/usr/local/lib/tzx-dram-gpu/runtime.py','guard'),end='',flush=True)
        print(run('python3','/usr/local/lib/tzx-pmic-poweroff/runtime.py','verify'),end='',flush=True)
        record=dict(state='installed',installed_boot_id=boot,toc0_sha256=pin,previous_toc0_sha256=OLD,
            raw_invariants=raw_pins,files=files,backup=str(BACKUP),ARM_emulation_verified=True,
            image_source_sha256=m['source_sha256'],canvas=[1280,800],orientation='right',
            picture_pixel_hash=m['native_bgra_sha256'],actual_boot_verification='pending')
        atomic(STATE,encoded(record));os.sync()
    except BaseException:
        for name,lba in (('toc0.bin',256),('dtb-sectors.bin',123194),('bundle-header.bin',98304),('active-header.bin',4096),('asset-before.bin',49152)):
            data=(BACKUP/name).read_bytes();os.pwrite(fd,data,lba*512)
        os.fsync(fd)
        for name,item in files.items():atomic(name,(BACKUP/'files'/name.lstrip('/')).read_bytes(),item['mode'])
        raise
    print('CUSTOM_BOOT_LOGO_INSTALLED_ALL_SECTORS_AND_FILE_GUARDS_VERIFIED',pin,flush=True)
finally:os.close(fd)
