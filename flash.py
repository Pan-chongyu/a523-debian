#!/usr/bin/env python3
"""One command: authenticated assets -> FEL installer -> verified USB image."""
import argparse,ctypes,json,os,secrets,subprocess,sys,time
from pathlib import Path
from flasher.core import flash_image,validate_manifest,verify_asset

REPOSITORY='Pan-chongyu/a523-debian'
VERSION='v0.1.0-20261114'
MESSAGES={
 'en':dict(title='A523 Debian flasher',board='Confirm the PCB is TZX P30A523_20T5G, LPDDR3 4GiB, UEM 128GB eMMC. This is NOT a universal A523 image.',
   erase='ALL DATA on the tablet eMMC will be replaced. Type FLASH to continue: ',download='Downloading and checking',fel='Enter FEL mode and connect exactly one tablet.',
   installer='Writing verified temporary installer',wait='Waiting for USB storage (up to 180 seconds)',write='Writing image with readback verification',
   done='Flash and readback completed. The first boot grows the root filesystem. Login: debian / debian. Change this password before enabling SSH.',
   reboot='Automatic reboot unavailable. Safely disconnect USB, then hold Power to restart.',dry='Dry run passed: no USB device opened and no disk written.'),
 'zh-CN':dict(title='A523 Debian 一键刷机',board='请确认板号 TZX P30A523_20T5G、LPDDR3 4GiB、UEM 128GB eMMC。本镜像仅适用于此硬件组合。',
   erase='平板 eMMC 的全部现有数据将被替换。输入 FLASH 继续：',download='正在下载并校验',fel='请进入 FEL 模式，并且只连接一台平板。',
   installer='正在写入并校验临时安装引导',wait='等待 USB 磁盘出现（最长180秒）',write='正在写入镜像并逐块读回校验',
   done='刷机和读回校验完成。首次启动会扩展根文件系统。登录：debian / debian。开启 SSH 前请更改密码。',
   reboot='无法自动重启。请安全断开 USB 后，长按电源重新启动。',dry='预演检查通过：未打开 USB 设备，未写入磁盘。'),
 'ja':dict(title='A523 Debian 書き込みツール',board='基板 TZX P30A523_20T5G、LPDDR3 4GiB、UEM 128GB eMMC を確認してください。他の A523 機種には対応しません。',
   erase='タブレットの eMMC データがすべて置き換えられます。続行するには FLASH と入力: ',download='ダウンロードと検証',fel='FEL モードのタブレットを1台だけ接続してください。',
   installer='一時インストーラーを書き込み・検証中',wait='USB ストレージを待機中（最大180秒）',write='イメージの書き込みと読み戻し検証中',
   done='書き込みと検証が完了しました。初回起動時にファイルシステムを拡張します。ログイン: debian / debian。SSH を有効にする前にパスワードを変更してください。',
   reboot='自動再起動できません。USB を安全に取り外し、電源ボタンで再起動してください。',dry='ドライラン成功。USB デバイスとディスクにはアクセスしていません。'),
 'es':dict(title='Instalador de Debian para A523',board='Confirma placa TZX P30A523_20T5G, LPDDR3 de4GiB y eMMC UEM de128GB. No sirve para todos los dispositivos A523.',
   erase='Se reemplazarán TODOS los datos de la eMMC. Escribe FLASH para continuar: ',download='Descargando y verificando',fel='Conecta una sola tableta en modo FEL.',
   installer='Escribiendo y verificando el instalador temporal',wait='Esperando almacenamiento USB (hasta180 segundos)',write='Escribiendo imagen y verificando cada bloque',
   done='Escritura y verificación completadas. El primer inicio amplía el sistema de archivos. Usuario/contraseña: debian / debian. Cambia la contraseña antes de activar SSH.',
   reboot='No se pudo reiniciar automáticamente. Desconecta USB de forma segura y reinicia con el botón de encendido.',dry='Simulación correcta: no se abrió ningún USB ni se escribió ningún disco.')}

def download(url,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.part')
    curl='curl.exe' if os.name=='nt' else 'curl'
    subprocess.run([curl,'--fail','--location','--show-error','--retry','3','--connect-timeout','20',
        '--continue-at','-','--output',str(temporary),url],check=True)
    temporary.replace(path)

def candidates():
    if os.name=='nt':
        command='@(Get-Disk | Where-Object BusType -eq USB | Select-Object Number,Size,IsBoot,IsSystem) | ConvertTo-Json -Compress'
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
        values=json.loads(result.stdout or '[]');values=[values] if isinstance(values,dict) else values
        return [(r'\\.\PhysicalDrive'+str(int(x['Number'])),int(x['Size']),int(x['Number'])) for x in values if not x['IsBoot'] and not x['IsSystem']]
    result=[]
    for path in Path('/dev/disk/by-id').glob('usb-*'):
        if '-part' in path.name:continue
        actual=path.resolve();size_path=Path('/sys/class/block')/actual.name/'size'
        if size_path.exists():result.append((str(actual),int(size_path.read_text())*512,None))
    return list(dict.fromkeys(result))

def find_target(nonce,sectors,seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        matched=[]
        for name,size,number in candidates():
            if size!=sectors*512:continue
            try:
                with open(name,'rb',buffering=0) as stream:
                    stream.seek(128*512);data=stream.read(512)
                if data[:len(nonce)]==nonce:matched.append((name,number))
            except OSError:continue
        if len(matched)>1:raise RuntimeError('More than one disk has the installer session nonce')
        if matched:return matched[0]
        time.sleep(2)
    raise TimeoutError('Installer USB storage not found; re-enter FEL and retry. No host disk was selected.')

def take_offline(number,target):
    if os.name=='nt':
        subprocess.run(['powershell.exe','-NoProfile','-Command',
            'Set-Disk -Number %d -IsOffline $true -ErrorAction Stop'%number],check=True)
    else:
        mounts=json.loads(subprocess.check_output(['lsblk','-J','-o','NAME,MOUNTPOINTS',target],text=True))
        def check(items):
            for item in items:
                if any(item.get('mountpoints') or []):raise RuntimeError('Unmount tablet partitions before flashing')
                check(item.get('children',[]))
        check(mounts['blockdevices'])

def reboot_installer(cid):
    import serial
    from serial.tools import list_ports
    ports=[p for p in list_ports.comports() if p.vid==0x1d6b and p.pid==0x0104 and p.serial_number=='TZX-P30A523-PUBLIC']
    if len(ports)!=1:return False
    with serial.Serial(ports[0].device,115200,timeout=.2,write_timeout=3) as link:
        command='\r\nsync; [ "$(cat /sys/class/block/mmcblk0/device/cid)" = "'+cid+'" ] && reboot -f\n'
        link.write(command.encode());time.sleep(.5)
    return True

def main():
    parser=argparse.ArgumentParser(description='TZX P30 A523 board-specific verified installer')
    parser.add_argument('--lang',choices=MESSAGES,default='zh-CN' if sys.platform=='win32' else 'en')
    parser.add_argument('--cache',type=Path,default=Path.home()/'.cache/a523-debian'/VERSION)
    parser.add_argument('--manifest',type=Path);parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--yes',action='store_true',help='Confirm erase AND the exact physical board profile')
    args=parser.parse_args();m=MESSAGES[args.lang];print(m['title'],flush=True)
    base='https://github.com/'+REPOSITORY+'/releases/download/'+VERSION
    manifest_path=args.manifest or args.cache/'release-manifest.json'
    if not manifest_path.exists():download(base+'/release-manifest.json',manifest_path)
    manifest=validate_manifest(json.loads(manifest_path.read_text(encoding='utf-8')))
    for item in manifest['files'].values():
        path=args.cache/item['name']
        if not path.exists():print(m['download'],item['name'],flush=True);download(base+'/'+item['name'],path)
        verify_asset(path,item)
    if args.dry_run:
        print(m['dry']);print(json.dumps(dict(image_bytes=manifest['image_uncompressed_bytes'],profile=manifest['board_profile'])));return
    if os.name=='nt' and not ctypes.windll.shell32.IsUserAnAdmin():raise PermissionError('Run the launcher as Administrator')
    if os.name!='nt' and os.geteuid()!=0:raise PermissionError('Run sudo ./flash.sh')
    print(m['board']);print(m['fel'])
    if not args.yes and input(m['erase']).strip()!='FLASH':raise SystemExit('Cancelled')
    from flasher.fel import Fel
    fel=Fel(args.cache/manifest['files']['helper']['name'])
    nonce=b'A523-DEBIAN-INSTALL-V1:'+secrets.token_bytes(32)
    def show(done,total):
        percent=done*100//total
        if percent!=getattr(show,'previous',None):print('%d%% (%d / %d)'%(percent,done,total),flush=True);show.previous=percent
    try:
        fel.connect();identity=fel.identify();print(json.dumps(identity),flush=True)
        print(m['installer'],flush=True)
        read=lambda key:(args.cache/manifest['files'][key]['name']).read_bytes()
        fel.bootstrap(read('installer'),read('toc0'),read('installer_header'),nonce,show)
        fel.reboot()
    finally:fel.close()
    print(m['wait'],flush=True);target,number=find_target(nonce,identity['sectors'])
    take_offline(number,target);print(m['write'],target,flush=True);show.previous=None
    flash_image(args.cache/manifest['files']['image']['name'],target,manifest,identity['sectors'],show)
    print(m['done'],flush=True)
    try:rebooted=reboot_installer(identity['cid'])
    except Exception:rebooted=False
    if not rebooted:print(m['reboot'],flush=True)

if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as error:
        print('ERROR:',str(error),file=sys.stderr);raise SystemExit(1)
