#!/usr/bin/env python3
"""Sanitize only an isolated staging tree, then regenerate exact runtime pins."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path

ORIGINAL_CID='3e01ff55454d20202010209170281b59'
sha=lambda data:hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--assets',type=Path,required=True);args=p.parse_args()
    root=args.root.resolve();assets=args.assets.resolve();assert root!=Path('/') and 'a523-public-release' in str(root)
    assert (root/'usr/bin/python3').exists() and not root.is_symlink()
    oldhash={};changes={}
    def write(name,data,mode=None):
        target=root/name.lstrip('/');assert not target.is_symlink(),name
        if target.exists():oldhash[name]=sha(target.read_bytes())
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        if mode is not None:target.chmod(mode)
        if name in oldhash:changes[oldhash[name]]=sha(data)
    # Export excludes homes. Reset account credentials with a published
    # password, not the device owner's original hash. Root remains locked.
    password_hash=subprocess.check_output(['openssl','passwd','-6','-stdin'],input=b'debian\n').decode().strip()
    accounts=[]
    for line in (root/'etc/passwd').read_text().splitlines():
        fields=line.split(':');name=fields[0]
        accounts.append(':'.join((name,password_hash if name=='debian' else '!', '20771','0','99999','7','','','')))
    write('/etc/shadow',('\n'.join(accounts)+'\n').encode(),0o640)
    groups=[]
    for line in (root/'etc/group').read_text().splitlines():
        fields=line.split(':');groups.append(':'.join((fields[0],'!', '',fields[3])))
    write('/etc/gshadow',('\n'.join(groups)+'\n').encode(),0o640)
    shadow_gid=int(next(line.split(':')[2] for line in (root/'etc/group').read_text().splitlines() if line.startswith('shadow:')))
    for name in ('shadow','gshadow'):os.chown(root/'etc'/name,0,shadow_gid)
    write('/etc/machine-id',b'',0o444)
    write('/etc/tzx-public-profile',b'tzx-p30a523-20t5g-lpddr3-4g-uem128\n',0o644)
    write('/etc/tzx-board-id',b'TZX P30A523_20T5G PUBLIC\n',0o644)
    write('/etc/sudoers.d/90-debian',b'debian ALL=(ALL:ALL) ALL\n',0o440)
    write('/etc/ssh/sshd_config.d/90-public-image.conf',b'PermitRootLogin no\nPasswordAuthentication yes\nPermitEmptyPasswords no\n',0o644)
    # SSH disabled until the user changes the known initial password and
    # explicitly starts it; USB serial remains available with normal login.
    for link in (root/'etc/systemd/system').rglob('*'):
        if link.is_symlink() and link.name in ('ssh.service','sshd.service','ssh.socket'):link.unlink()
    for folder in ('root','home/debian/.ssh','home/debian/.cache','home/debian/.mozilla',
        'home/debian/.config/mozilla','home/debian/.local/share/keyrings',
        'etc/NetworkManager/system-connections','var/lib/bluetooth','var/lib/NetworkManager',
        'var/log','var/cache','var/tmp','var/backups','var/lib/apt/lists'):
        path=root/folder
        if path.exists() and not path.is_symlink():shutil.rmtree(path)
        path.mkdir(parents=True,exist_ok=True)
    (root/'root').chmod(0o700);(root/'etc/NetworkManager/system-connections').chmod(0o700)
    for key in (root/'etc/ssh').glob('ssh_host_*'):key.unlink()
    home=root/'home/debian';home.mkdir(exist_ok=True);home.chmod(0o755)
    for name in ('.profile','.bashrc','.bash_logout'):
        if (root/'etc/skel'/name).exists():shutil.copy2(root/'etc/skel'/name,home/name)
    for path in home.rglob('*'):
        if not path.is_symlink():os.chown(path,1000,1000)
    os.chown(home,1000,1000)
    for folder in ('dev','proc','sys','run','tmp','mnt','media'):(root/folder).mkdir(exist_ok=True)
    (root/'tmp').chmod(0o1777);(root/'var/tmp').chmod(0o1777)
    for base in ('usr/local','home/debian'):
        for folder in list((root/base).rglob('__pycache__')):
            if folder.is_dir() and not folder.is_symlink():shutil.rmtree(folder)
    # Exported home scripts include many past experiments. Keep only scripts
    # referenced by system configuration/runtime, including transitive helpers.
    referenced=set()
    texts=[]
    for base in ('usr/local','etc/systemd','etc/lightdm','etc/xdg'):
        for file in (root/base).rglob('*'):
            if file.is_file() and not file.is_symlink() and file.stat().st_size<2000000:
                try:texts.append(file.read_text())
                except UnicodeDecodeError:pass
    while True:
        before=len(referenced)
        for text in texts:
            referenced.update(re.findall(r'/home/debian/([A-Za-z0-9_.-]+\.py)',text))
        for name in sorted(referenced):
            file=home/name
            if file.exists():
                try:texts.append(file.read_text())
                except UnicodeDecodeError:pass
        if len(referenced)==before:break
    for file in home.glob('*.py'):
        if file.name not in referenced:file.unlink()
    obsolete=root/'usr/local/lib/tzx-dram-c-step'
    if obsolete.exists():shutil.rmtree(obsolete)
    # Bind Python guards to the actual allowed card CID written by initramfs.
    cid_expression="Path('/etc/tzx/device-cid').read_text().strip()"
    for base in ('usr/local','home/debian'):
        for file in (root/base).rglob('*'):
            if not file.is_file() or file.is_symlink() or file.suffix not in ('.py','.sh',''):continue
            data=file.read_bytes()
            try:text=data.decode()
            except UnicodeDecodeError:continue
            if ORIGINAL_CID not in text:continue
            if file.suffix=='.py':
                # Guard scripts already import Path; this also updates their
                # expected board identity strings without disabling checking.
                text=text.replace("'"+ORIGINAL_CID+"'",cid_expression)
                text=text.replace('"'+ORIGINAL_CID+'"',cid_expression)
            else:text=text.replace(ORIGINAL_CID,'$(cat /etc/tzx/device-cid)')
            write('/'+file.relative_to(root).as_posix(),text.encode())
    write('/usr/local/sbin/tzx-enable-cpub',(assets/'tzx-enable-cpub').read_bytes(),0o755)
    write('/boot/Image',(assets/'Image').read_bytes(),0o644)
    write('/boot/board.dtb',(assets/'board.dtb').read_bytes(),0o644)
    write('/boot/initramfs.cpio.gz',(assets/'initramfs.cpio.gz').read_bytes(),0o644)
    write('/usr/local/lib/tzx-emmc-hs/tzx_emmc_hs_lease.ko',(assets/'tzx_emmc_hs_lease.ko').read_bytes(),0o644)
    boot=json.loads((assets/'boot-build.json').read_text())
    changes.update({'fc208e752fc816e1e016944cd0f4c4d9497989ec174718e5f3b12d030136b0ca':boot['toc0_sha256'],
        '48c684a6c07712b66b28f65da5927ff415dd4e72cea91eea30e009b0e932dab7':boot['header_sha256']})
    # Hardware code keeps immutable file hashes. Update dependencies until
    # their DAG reaches a fixed point; never replace checks with unconditional
    # success. Read-only qualification history remains labeled as baseline.
    tracked=[]
    for base in ('usr/local','home/debian','var/lib/tzx'):
        for file in (root/base).rglob('*'):
            if file.is_file() and not file.is_symlink() and file.stat().st_size<2*1024*1024:
                try:file.read_text()
                except (UnicodeDecodeError,OSError):continue
                tracked.append(file)
    for iteration in range(24):
        changed=0
        for file in tracked:
            data=file.read_bytes();text=data.decode();new=re.sub(r'\b[0-9a-f]{64}\b',lambda m:changes.get(m[0],m[0]),text)
            if new!=text:
                file.write_text(new);changes[sha(data)]=sha(new.encode());changed+=1
        if not changed:break
    else:raise RuntimeError('Pin dependency graph did not converge')
    # Correct direct metadata fields whose source state had older loader pins.
    panel=root/'var/lib/tzx/boot-panel-installed.json'
    value=json.loads(panel.read_text());value['toc0_sha256']=boot['toc0_sha256'];panel.write_text(json.dumps(value,indent=2)+'\n')
    script=Path(__file__).parent/'firstboot.py'
    write('/usr/local/sbin/tzx-public-firstboot',script.read_bytes(),0o755)
    unit=b'[Unit]\nDescription=Initialize unique public image identities\nBefore=lightdm.service\nAfter=local-fs.target\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/tzx-public-firstboot\n[Install]\nWantedBy=multi-user.target\n'
    write('/etc/systemd/system/tzx-public-firstboot.service',unit,0o644)
    wants=root/'etc/systemd/system/multi-user.target.wants/tzx-public-firstboot.service'
    if wants.is_symlink():wants.unlink()
    wants.symlink_to('../tzx-public-firstboot.service')
    for file in (root/'etc/systemd/system').glob('*diagnostic*'):
        if file.is_file():file.unlink()
    # Scan the staged tree, not live paths. No SSH authorized_keys or private
    # key material is permitted in any included regular file.
    violations=[]
    for base in ('etc','home','root','var/lib/tzx','usr/local'):
        for file in (root/base).rglob('*'):
            if not file.is_file() or file.is_symlink():continue
            if file.name in ('authorized_keys','known_hosts','.bash_history'):violations.append(str(file))
            if file.stat().st_size<2*1024*1024:
                data=file.read_bytes()
                if any(marker in data for marker in (b'-----BEGIN OPENSSH PRIVATE KEY-----',b'-----BEGIN PRIVATE KEY-----',b'psk=')):
                    violations.append(str(file))
    assert not violations,violations
    report=dict(public_profile='tzx-p30a523-20t5g-lpddr3-4g-uem128',default_login='debian',default_password='debian',
        root_locked=True,ssh_disabled=True,no_original_credentials=True,hash_dependencies_updated=len(changes),
        public_variant_hardware_tested=False,hardware_qualification_scope='original unit before sanitization and CID-prefix changes')
    (assets/'sanitization-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PUBLIC_STAGING_SANITIZED',json.dumps(report),flush=True)

if __name__=='__main__':main()
