"""Native desktop front end; no device access until explicit erasure consent."""
import argparse,ctypes,json,os,queue,sys,threading,time,webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox,ttk
from tkinter.scrolledtext import ScrolledText
import flash

TOOL_VERSION='v0.2.0'
LANGUAGES={'简体中文':'zh-CN','English':'en','日本語':'ja','Español':'es'}
TEXT={
 'zh-CN':dict(title='A523 Debian 一键刷机',subtitle='连接平板，自动完成镜像下载、校验和刷写。',
   steps='① 进入 FEL 模式    →    ② 连接 USB 数据线    →    ③ 开始刷机',
   board='仅支持 TZX P30A523_20T5G · LPDDR3 4 GiB · UEM 128 GB eMMC',
   profile='JL_M1010WX92_M4027 屏幕 · 默认向右横屏 · Debian 13 XFCE',
   consent='我已核对主板型号，并了解刷机会清空平板全部现有数据',
   start='开始刷机',check='只下载并检查',cancel='取消下载',help='刷机教程',driver='FEL 驱动说明',
   ready='准备就绪',hint='将平板置于 FEL 模式，只连接一台目标设备。首次使用请先阅读驱动说明。',
   notice='实验性公开镜像：已通过自动检查，尚未完成整包实机重刷验证。',
   confirm='即将替换这台平板 eMMC 上的全部现有数据。\n\n确认主板为 TZX P30A523_20T5G、4 GiB LPDDR3、UEM 128 GB？\n请保持 USB 连接及供电，刷写阶段不要关闭程序。',
   need_consent='请先核对并勾选主板型号与清空确认。',admin='请右键程序选择“以管理员身份运行”。',
   asset='准备文件 {index}/{total}：{name}',download='正在下载镜像 / 安装文件',verify='正在校验 SHA256：{name}',
   device='正在识别 FEL 设备与 eMMC',identity='设备容量与 eMMC 产品检查通过',install='正在写入并校验临时安装引导',
   wait='等待平板切换为 USB 安装磁盘，最长 180 秒……',write='正在写入系统镜像并逐块读回校验',reboot='正在完成写入并尝试重启',
   checked='下载和校验完成。未打开 USB 设备，未写入磁盘。',done='刷机完成，所有写入块均通过读回校验。',
   after='首次启动会扩展文件系统。登录账号 / 密码：debian / debian；SSH 默认关闭。',
   manual='请安全断开 USB，再长按电源重新启动。',failed='操作失败',retry='请查看下方错误。若已进入刷写阶段，请重新进入 FEL 后重试。',
   cancelled='下载已取消，可再次运行以继续下载。',locked='刷写正在进行，请保持供电并等待完成。',log='操作记录',
   downloads='镜像缓存',license='软件许可',completed='完成',no_fel='当前未检测到 FEL 设备 (1f3a:efe8)',
   one_fel='已检测到 1 台 FEL 设备',many_fel='检测到多台 FEL 设备，请只保留一台',probe_error='USB 检测失败，请检查 WinUSB 驱动',
   close_busy='请先取消下载并等待任务结束，再关闭程序。'),
 'en':dict(title='A523 Debian Flasher',subtitle='Connect the tablet. Download, verify and install automatically.',
   steps='1  Enter FEL mode    →    2  Connect USB    →    3  Start flashing',
   board='TZX P30A523_20T5G only · 4 GiB LPDDR3 · UEM 128 GB eMMC',
   profile='JL_M1010WX92_M4027 display · Right landscape · Debian 13 XFCE',
   consent='I verified the board model and understand all tablet data will be replaced',
   start='Start flashing',check='Download and check only',cancel='Cancel download',help='Flashing guide',driver='FEL driver help',
   ready='Ready',hint='Enter FEL mode and connect exactly one tablet. Read driver help on first use.',
   notice='Experimental public image: automated checks passed; full hardware reflash is untested.',
   confirm='ALL existing data on the tablet eMMC will be replaced.\n\nIs the board TZX P30A523_20T5G, 4 GiB LPDDR3, UEM 128 GB?\nKeep USB and power connected. Do not close the app while writing.',
   need_consent='Verify and check the board / data-erasure confirmation first.',admin='Right-click the program and select Run as administrator.',
   asset='Preparing file {index}/{total}: {name}',download='Downloading image / installer',verify='Checking SHA256: {name}',
   device='Identifying FEL device and eMMC',identity='Capacity and eMMC product checks passed',install='Writing and verifying temporary installer',
   wait='Waiting for installer USB storage, up to 180 seconds…',write='Writing the image with block readback verification',reboot='Finishing writes and attempting reboot',
   checked='Download and verification complete. No USB device opened or disk written.',done='Flashing complete. All written blocks passed readback.',
   after='First boot expands the filesystem. Login: debian / debian. SSH is disabled.',
   manual='Safely disconnect USB, then restart by holding Power.',failed='Operation failed',retry='See the error below. If writing began, re-enter FEL and retry.',
   cancelled='Download cancelled. Run again to resume.',locked='Writing is in progress. Keep power connected and wait.',log='Activity',
   downloads='Image cache',license='Licenses',completed='Complete',no_fel='No FEL device detected (1f3a:efe8)',
   one_fel='One FEL device detected',many_fel='Multiple FEL devices detected; connect only one',probe_error='USB detection failed; check the WinUSB driver',
   close_busy='Cancel the download and wait for the task to finish before closing.'),
 'ja':dict(title='A523 Debian 書き込みツール',subtitle='接続後、ダウンロード・検証・書き込みを自動で実行します。',
   steps='① FEL モード    →    ② USB 接続    →    ③ 書き込み開始',
   board='TZX P30A523_20T5G 専用 · LPDDR3 4 GiB · UEM 128 GB eMMC',
   profile='JL_M1010WX92_M4027 画面 · 右回転の横画面 · Debian 13 XFCE',
   consent='基板型番を確認し、タブレットの全データが置き換わることを理解しました',
   start='書き込み開始',check='ダウンロードと検証のみ',cancel='ダウンロード中止',help='手順',driver='FEL ドライバー',
   ready='準備完了',hint='FEL モードにして1台だけ接続してください。初回はドライバー手順を確認してください。',
   notice='実験的イメージ：自動検査済み。公開版の実機への全体書き込みは未検証です。',
   confirm='eMMC の既存データをすべて置き換えます。\n\nTZX P30A523_20T5G、LPDDR3 4 GiB、UEM 128 GB ですか？\nUSB と電源を維持し、書き込み中は終了しないでください。',
   need_consent='基板型番とデータ消去の確認をチェックしてください。',admin='右クリックし「管理者として実行」を選択してください。',
   asset='ファイル準備 {index}/{total}: {name}',download='イメージをダウンロード中',verify='SHA256 検証中: {name}',
   device='FEL と eMMC を確認中',identity='容量・製品の確認に成功',install='一時インストーラーを書き込み・検証中',
   wait='USB ストレージを待機中（最大180秒）…',write='イメージを書き込み、ブロックを読み戻し検証中',reboot='書き込みを完了して再起動中',
   checked='ダウンロードと検証が完了。USB やディスクにはアクセスしていません。',done='書き込みと全ブロックの読み戻し検証が完了しました。',
   after='初回起動で領域を拡張します。ログイン: debian / debian。SSH は無効です。',
   manual='USB を安全に外し、電源ボタンを長押しして再起動してください。',failed='処理に失敗しました',retry='下のエラーを確認してください。書き込み開始後の場合は FEL に戻して再試行してください。',
   cancelled='中止しました。再実行するとダウンロードを再開します。',locked='書き込み中です。電源を維持してお待ちください。',log='処理記録',
   downloads='キャッシュ',license='ライセンス',completed='完了',no_fel='FEL デバイスがありません (1f3a:efe8)',
   one_fel='FEL デバイスを1台検出',many_fel='FEL デバイスは1台だけ接続してください',probe_error='USB 検出失敗。WinUSB を確認してください',
   close_busy='ダウンロードを中止し、処理の終了後に閉じてください。'),
 'es':dict(title='Instalador de Debian A523',subtitle='Conecta la tableta. Descarga, verifica e instala automáticamente.',
   steps='1  Modo FEL    →    2  Conectar USB    →    3  Iniciar instalación',
   board='Solo TZX P30A523_20T5G · LPDDR3 de 4 GiB · eMMC UEM de 128 GB',
   profile='Pantalla JL_M1010WX92_M4027 · Horizontal a la derecha · Debian 13 XFCE',
   consent='Verifiqué la placa y entiendo que se reemplazarán todos los datos de la tableta',
   start='Iniciar instalación',check='Solo descargar y verificar',cancel='Cancelar descarga',help='Guía',driver='Controlador FEL',
   ready='Preparado',hint='Conecta una sola tableta en modo FEL. Consulta el controlador para el primer uso.',
   notice='Imagen experimental: verificaciones automáticas superadas; instalación completa en hardware sin probar.',
   confirm='Se reemplazarán TODOS los datos de la eMMC.\n\n¿Es TZX P30A523_20T5G, LPDDR3 de 4 GiB, UEM de 128 GB?\nMantén USB y alimentación. No cierres durante la escritura.',
   need_consent='Confirma primero la placa y el reemplazo de datos.',admin='Haz clic derecho y selecciona Ejecutar como administrador.',
   asset='Preparando {index}/{total}: {name}',download='Descargando imagen / instalador',verify='Verificando SHA256: {name}',
   device='Identificando FEL y eMMC',identity='Capacidad y producto eMMC verificados',install='Escribiendo y verificando instalador temporal',
   wait='Esperando almacenamiento USB, hasta 180 segundos…',write='Escribiendo y verificando cada bloque',reboot='Finalizando e intentando reiniciar',
   checked='Descarga y verificación completas. No se abrió USB ni se escribió ningún disco.',done='Instalación completa. Todos los bloques verificados.',
   after='El primer inicio amplía el sistema. Acceso: debian / debian. SSH desactivado.',
   manual='Desconecta USB de forma segura y reinicia manteniendo el botón de encendido.',failed='Operación fallida',retry='Consulta el error. Si comenzó la escritura, vuelve a FEL y reintenta.',
   cancelled='Descarga cancelada. Ejecuta de nuevo para continuar.',locked='Escritura en curso. Mantén la alimentación y espera.',log='Actividad',
   downloads='Caché',license='Licencias',completed='Completo',no_fel='No se detecta FEL (1f3a:efe8)',
   one_fel='Una tableta FEL detectada',many_fel='Hay varias tabletas FEL; conecta solo una',probe_error='Error USB; comprueba el controlador WinUSB',
   close_busy='Cancela la descarga y espera a que termine antes de cerrar.')}


def bundled_root():
    return Path(__file__).resolve().parents[1]


def probe_fel():
    """Enumerate USB descriptors only; never claim, execute or write a device."""
    import libusb_package
    count=len(list(libusb_package.find(find_all=True,idVendor=0x1f3a,idProduct=0xefe8)))
    return 'no_fel' if count==0 else 'one_fel' if count==1 else 'many_fel'


def dependency_check():
    import libusb_package,serial,usb.core
    if libusb_package.get_libusb1_backend() is None:raise RuntimeError('Bundled libusb backend could not be loaded')
    manifest=json.loads((bundled_root()/'board/release-manifest.json').read_text(encoding='utf-8'))
    flash.validate_manifest(manifest)
    if manifest['version']!=flash.VERSION:raise ValueError('Bundled image version mismatch')
    return dict(tool_version=TOOL_VERSION,image_version=flash.VERSION,libusb_backend=True,
        python_bundled=bool(getattr(sys,'frozen',False)),tk_version=tk.Tcl().eval('info patchlevel'))


class Application:
    def __init__(self,root,lang,cache):
        self.root=root;self.lang=lang;self.cache=Path(cache);self.events=queue.Queue()
        self.cancel=threading.Event();self.critical=threading.Event();self.busy=False;self.probing=False
        self.consent=tk.BooleanVar(value=False);self.language=tk.StringVar(value=next(k for k,v in LANGUAGES.items() if v==lang))
        self.status=tk.StringVar();self.detail=tk.StringVar();self.usb_status=tk.StringVar()
        root.title('A523 Debian Flasher '+TOOL_VERSION);root.geometry('900x740');root.minsize(840,710)
        icon=bundled_root()/'packaging/flasher.ico'
        if os.name=='nt' and icon.exists():root.iconbitmap(str(icon))
        root.configure(background='#f3f5fa');root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style();style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background='#f3f5fa',foreground='#18243a')
        style.configure('Card.TFrame',background='white');style.configure('Card.TLabel',background='white')
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',23,'bold'))
        style.configure('Muted.TLabel',foreground='#56657c');style.configure('CardMuted.TLabel',foreground='#56657c',background='white')
        style.configure('Primary.TButton',background='#265fde',foreground='white',padding=(24,12),font=('Microsoft YaHei UI',11,'bold'))
        style.map('Primary.TButton',background=[('active','#1c4cbe'),('disabled','#aabbdc')])
        style.configure('TButton',padding=(14,9));style.configure('Horizontal.TProgressbar',background='#265fde',troughcolor='#e6ebf5',borderwidth=0)
        outer=ttk.Frame(root,padding=28);outer.pack(fill='both',expand=True)
        top=ttk.Frame(outer);top.pack(fill='x')
        self.heading=ttk.Label(top,style='Title.TLabel');self.heading.pack(side='left')
        self.selector=ttk.Combobox(top,textvariable=self.language,values=list(LANGUAGES),width=12,state='readonly')
        self.selector.pack(side='right');self.selector.bind('<<ComboboxSelected>>',self.change_language)
        self.subtitle=ttk.Label(outer,style='Muted.TLabel');self.subtitle.pack(anchor='w',pady=(6,16))
        self.steps=ttk.Label(outer,font=('Microsoft YaHei UI',11,'bold'));self.steps.pack(anchor='w',pady=(0,16))
        card=ttk.Frame(outer,style='Card.TFrame',padding=18);card.pack(fill='x')
        self.board=ttk.Label(card,style='Card.TLabel',font=('Microsoft YaHei UI',10,'bold'));self.board.pack(anchor='w')
        self.profile=ttk.Label(card,style='CardMuted.TLabel');self.profile.pack(anchor='w',pady=(6,10))
        ttk.Label(card,textvariable=self.usb_status,style='Card.TLabel').pack(anchor='w')
        self.hint=ttk.Label(outer,wraplength=820,style='Muted.TLabel');self.hint.pack(anchor='w',pady=(12,8))
        self.check_consent=ttk.Checkbutton(outer,variable=self.consent,command=self.update_buttons)
        self.check_consent.pack(anchor='w',pady=(3,12))
        buttons=ttk.Frame(outer);buttons.pack(fill='x')
        self.start_button=ttk.Button(buttons,style='Primary.TButton',command=self.start_flash);self.start_button.pack(side='left')
        self.check_button=ttk.Button(buttons,command=lambda:self.begin(False));self.check_button.pack(side='left',padx=10)
        self.cancel_button=ttk.Button(buttons,command=self.cancel_download);self.cancel_button.pack(side='left')
        ttk.Label(outer,textvariable=self.status,font=('Microsoft YaHei UI',11,'bold'),wraplength=815).pack(anchor='w',pady=(18,6))
        self.progress=ttk.Progressbar(outer,maximum=100);self.progress.pack(fill='x')
        ttk.Label(outer,textvariable=self.detail,style='Muted.TLabel',wraplength=815).pack(anchor='w',pady=(6,12))
        self.log_label=ttk.Label(outer);self.log_label.pack(anchor='w')
        self.log=ScrolledText(outer,height=6,font=('Consolas',9),background='white',relief='flat',wrap='word',state='disabled')
        self.log.pack(fill='both',expand=True,pady=(5,10))
        footer=ttk.Frame(outer);footer.pack(fill='x')
        self.help_button=ttk.Button(footer,command=self.open_guide);self.help_button.pack(side='left')
        self.driver_button=ttk.Button(footer,command=self.open_driver);self.driver_button.pack(side='left',padx=6)
        self.license_button=ttk.Button(footer,command=self.open_licenses);self.license_button.pack(side='left')
        ttk.Label(footer,text=TOOL_VERSION+'  ·  Windows x64',style='Muted.TLabel').pack(side='right')
        self.notice=ttk.Label(outer,wraplength=815,style='Muted.TLabel');self.notice.pack(anchor='w',pady=(10,0))
        self.apply_text();self.update_buttons();root.after(100,self.poll);root.after(300,self.start_probe)

    def text(self,key):return TEXT[self.lang][key]

    def apply_text(self):
        for name,key in [('heading','title'),('subtitle','subtitle'),('steps','steps'),('board','board'),('profile','profile'),
            ('hint','hint'),('check_consent','consent'),('start_button','start'),('check_button','check'),('cancel_button','cancel'),
            ('help_button','help'),('driver_button','driver'),('license_button','license'),('log_label','log'),('notice','notice')]:
            getattr(self,name).configure(text=self.text(key))
        self.status.set(self.text('ready'));self.detail.set(self.text('downloads')+': '+str(self.cache));self.usb_status.set(self.text('no_fel'))

    def change_language(self,event=None):
        self.lang=LANGUAGES[self.language.get()];self.apply_text()

    def update_buttons(self):
        self.start_button.configure(state='normal' if self.consent.get() and not self.busy else 'disabled')
        self.check_button.configure(state='disabled' if self.busy else 'normal')
        self.cancel_button.configure(state='normal' if self.busy and not self.critical.is_set() and not self.cancel.is_set() else 'disabled')
        self.check_consent.configure(state='disabled' if self.busy else 'normal')
        self.selector.configure(state='disabled' if self.busy else 'readonly')

    def start_probe(self):
        if not self.busy and not self.probing:
            self.probing=True
            def run():
                try:self.events.put(('probe',dict(key=probe_fel())))
                except Exception:self.events.put(('probe',dict(key='probe_error')))
            threading.Thread(target=run,daemon=True).start()
        self.root.after(5000,self.start_probe)

    def append(self,line):
        self.log.configure(state='normal');self.log.insert('end',time.strftime('%H:%M:%S')+'  '+line+'\n');self.log.see('end');self.log.configure(state='disabled')

    def start_flash(self):
        if not self.consent.get():messagebox.showwarning(self.text('title'),self.text('need_consent'),parent=self.root);return
        if os.name=='nt' and not ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showerror(self.text('title'),self.text('admin'),parent=self.root);return
        if messagebox.askokcancel(self.text('start'),self.text('confirm'),icon='warning',default='cancel',parent=self.root):self.begin(True)

    def begin(self,write):
        if self.busy:return
        if write and not self.consent.get():raise PermissionError('Board and erasure consent required')
        self.busy=True;self.cancel.clear();self.critical.clear();self.progress['value']=0;self.update_buttons()
        def notify(event,data):
            if event=='install':self.critical.set()
            self.events.put((event,data))
        def work():
            try:
                manifest=flash.prepare_assets(self.cache,notify=notify,cancel=self.cancel)
                rebooted=flash.install(self.cache,manifest,confirmed=True,notify=notify,cancel=self.cancel) if write else None
                notify('finished',dict(write=write,rebooted=rebooted))
            except flash.Cancelled:notify('cancelled',{})
            except Exception as error:notify('error',dict(error=str(error)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        for _ in range(100):
            try:event,data=self.events.get_nowait()
            except queue.Empty:break
            if event=='probe':
                self.probing=False
                if not self.busy:self.usb_status.set(self.text(data['key']))
            elif event in ('asset','verify'):
                label=self.text(event).format(**data);self.status.set(label);self.append(label)
                if event=='asset':self.progress['value']=0
            elif event in ('download','progress'):
                if data['total']:
                    percent=data['done']*100/data['total'];self.progress['value']=percent
                    self.detail.set('%.1f%%   %.1f / %.1f MiB'%(percent,data['done']/1024**2,data['total']/1024**2))
                if event=='download':self.status.set(self.text('download'))
            elif event in ('device','identity','install','wait','write','reboot'):
                self.status.set(self.text(event));self.append(self.text(event));self.progress['value']=0;self.update_buttons()
            elif event in ('finished','cancelled','error'):
                self.busy=False;self.critical.clear();self.update_buttons()
                if event=='finished':
                    key='done' if data['write'] else 'checked';self.status.set(self.text(key));self.append(self.text(key));self.progress['value']=100
                    if data['write']:
                        extra=self.text('after')+('' if data['rebooted'] else '\n'+self.text('manual'))
                        self.detail.set(extra);self.append(extra)
                    else:self.detail.set(self.text('downloads')+': '+str(self.cache))
                elif event=='cancelled':self.status.set(self.text('cancelled'));self.append(self.text('cancelled'))
                else:
                    self.status.set(self.text('failed'));self.detail.set(self.text('retry'));self.append(data['error'])
                    messagebox.showerror(self.text('failed'),data['error'],parent=self.root)
        self.root.after(100,self.poll)

    def cancel_download(self):
        if self.busy and not self.critical.is_set():self.cancel.set();self.update_buttons()

    def close(self):
        if self.busy:
            messagebox.showinfo(self.text('title'),self.text('locked' if self.critical.is_set() else 'close_busy'),parent=self.root);return
        self.root.destroy()

    def open_guide(self):
        webbrowser.open('https://github.com/'+flash.REPOSITORY+'/blob/main/docs/'+self.lang+'/FLASHING.md')

    def open_driver(self):
        # The guide links Zadig and identifies exactly which interface to bind.
        self.open_guide()

    def open_licenses(self):
        path=bundled_root()/'WINDOWS-NOTICES.txt'
        if path.exists() and os.name=='nt':os.startfile(path)
        else:webbrowser.open('https://github.com/'+flash.REPOSITORY+'/blob/main/THIRD_PARTY.md')


def main():
    p=argparse.ArgumentParser(description='Standalone A523 Debian graphical flasher')
    p.add_argument('--lang',choices=TEXT,default='zh-CN');p.add_argument('--cache',type=Path,default=Path.home()/'.cache/a523-debian'/flash.VERSION)
    p.add_argument('--self-test',action='store_true',help='Check bundled dependencies and cached/downloaded assets; never open USB or disks')
    p.add_argument('--dependency-check',action='store_true',help='Check bundled Python/Tk/USB libraries without downloading assets or opening USB')
    p.add_argument('--report',type=Path)
    args=p.parse_args()
    if args.self_test or args.dependency_check:
        report=dict(success=False,usb_opened=False,disk_written=False)
        try:
            report.update(dependency_check())
            if args.self_test:
                manifest=flash.prepare_assets(args.cache)
                report.update(assets_verified=len(manifest['files']),image_bytes=manifest['image_uncompressed_bytes'])
            report['success']=True
        except Exception as error:report['error']=str(error)
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        if sys.stdout:print(json.dumps(report))
        return 0 if report['success'] else 1
    try:
        if os.name=='nt':
            try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:pass
        root=tk.Tk();Application(root,args.lang,args.cache);root.mainloop();return 0
    except Exception as error:
        messagebox.showerror('A523 Debian Flasher',str(error));return 1
