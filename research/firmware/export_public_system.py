"""Export a clean system template without user secrets; never write raw eMMC."""
import gzip,hashlib,io,json,os,re,stat,subprocess,tarfile,time
from pathlib import Path

assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
destination=Path('/var/tmp/tzx-public-export');destination.mkdir(mode=0o700,exist_ok=True)
target=destination/'system-template.tar.gz';assert not target.exists()
excluded={
    'etc/shadow','etc/shadow-','etc/gshadow','etc/gshadow-','etc/machine-id',
    'etc/NetworkManager/system-connections','etc/NetworkManager/secret_key',
    'etc/apt/auth.conf','etc/apt/auth.conf.d','etc/wpa_supplicant',
    'etc/sudoers.d','etc/ssl/private','etc/ppp/pap-secrets','etc/ppp/chap-secrets',
    'var/log','var/cache','var/tmp','var/backups','var/mail','var/spool',
    'var/lib/bluetooth','var/lib/NetworkManager','var/lib/AccountsService/users',
    'var/lib/dbus/machine-id','var/lib/systemd/random-seed','var/lib/systemd/coredump',
    'var/lib/lightdm','var/lib/dhcp','var/lib/private','usr/local/src',
}
seen=set();count=0;total=0

def allowed(name):
    if any(name==item or name.startswith(item+'/') for item in excluded):return False
    if name.startswith('etc/ssh/ssh_host_'):return False
    if name.startswith('etc/apt/apt.conf.d/') and any(word in name.lower() for word in ('proxy','auth')):return False
    if name.startswith('var/lib/tzx/'):
        basename=name.rsplit('/',1)[-1]
        # Current startup markers/guard receipts, not diagnostic captures.
        return basename in {'gpu-qualified','screen-qualified.json','cpu-full-qualified.json',
            'gpu-devfreq-qualified.json','emmc-hs-qualified.json','cpu-performance-qualified.json',
            'cpu-dvfs-qualified.json','gpu-performance-qualified.json','screen-display-setup.json'} or basename.endswith('-installed.json')
    return True

def filter_member(member):
    global count,total
    name=member.name.lstrip('./')
    if not allowed(name) or member.isdev() or member.isfifo():return None
    if name in seen:return None
    seen.add(name);count+=1;total+=member.size
    # Avoid leaking the original password hashes even in exported backup files.
    if 'shadow' in name.lower() and name not in ('etc/pam.d/common-password',):
        if name.startswith(('etc/','var/')):return None
    return member

with tarfile.open(target,'w:gz',compresslevel=1,dereference=False) as archive:
    for top in ('bin','boot','etc','lib','lib64','opt','sbin','usr','var'):
        path=Path('/'+top)
        if path.exists() or path.is_symlink():archive.add(path,arcname=top,filter=filter_member)
    # Runtime scripts referenced by the current services. No home directories,
    # shell history, browser profiles, saved recordings or user documents.
    for path in sorted(Path('/home/debian').glob('*.py')):
        data=path.read_bytes()
        if any(value in data.lower() for value in (b'psk=',b'password =',b'password=',b'passwd=',b'authorization: bearer')):continue
        archive.add(path,arcname='home/debian/'+path.name,filter=filter_member)
    for folder in ('.config/autostart','.local/share/applications'):
        for path in sorted((Path('/home/debian')/folder).glob('*.desktop')):
            archive.add(path,arcname='home/debian/'+folder+'/'+path.name,filter=filter_member)
    # Export inventories without credentials. Sources and package licenses are
    # retained under /usr/share/doc in the system tree.
    packages=subprocess.check_output(['dpkg-query','-W','-f',
        '${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n'])
    item=tarfile.TarInfo('release-inventory/packages.tsv');item.mode=0o644;item.size=len(packages)
    archive.addfile(item,io.BytesIO(packages))
raw={};descriptor=os.open('/dev/mmcblk0',os.O_RDONLY)
try:
    for name,lba,size in (('toc0.bin',256,49152),('logo.bin',49152,925696),
        ('header.bin',4096,512),('active-bundle.bin',98304,15008768),('fallback-bundle.bin',65536,15008768)):
        data=os.pread(descriptor,size,lba*512);assert len(data)==size
        (destination/name).write_bytes(data);raw[name]=dict(lba=lba,bytes=size,sha256=hashlib.sha256(data).hexdigest())
finally:os.close(descriptor)
digest=hashlib.sha256()
with target.open('rb') as stream:
    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
record=dict(source_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    created_unix=int(time.time()),archive_bytes=target.stat().st_size,archive_sha256=digest.hexdigest(),
    entries=count,uncompressed_file_bytes=total,raw=raw,original_password_hashes_exported=False,
    user_home_directories_exported=False,raw_emmc_writes=False)
(destination/'export.json').write_text(json.dumps(record,indent=2)+'\n')
for path in destination.iterdir():path.chmod(0o644)
destination.chmod(0o755)
print('CLEAN_SYSTEM_TEMPLATE_EXPORTED',json.dumps(record),flush=True)
