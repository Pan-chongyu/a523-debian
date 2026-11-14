#!/usr/bin/env python3
"""Build the standalone executable on Windows, without private project files."""
import argparse,hashlib,importlib.metadata,json,os,subprocess,sys
from pathlib import Path

def notices(root,out):
    sections=[(root/'LICENSE').read_text(encoding='utf-8'),
        '\nWindows executable dependencies\n===============================\n',
        'CPython: Python Software Foundation license. Tcl/Tk: Tcl/Tk license.\n'
        'PyUSB: BSD-3-Clause. pySerial: BSD-3-Clause. libusb-package: Apache-2.0.\n'
        'libusb 1.0.26 DLL: LGPL-2.1-or-later, dynamically loaded; matching source accompanies the executable release.\n'
        'PyInstaller: GPL-2.0-or-later with its bootloader distribution exception.\n'
        'Sources/build recipe: https://github.com/Pan-chongyu/a523-debian/tree/main/packaging\n']
    for name in ('pyusb','libusb-package','importlib_resources','pyinstaller'):
        distribution=importlib.metadata.distribution(name)
        for file in distribution.files or []:
            if file.name.lower() in ('license','license.txt','copying','copying.txt'):
                path=Path(distribution.locate_file(file))
                sections.append('\n--- '+name+' '+distribution.version+' / '+str(file)+' ---\n'+path.read_text(encoding='utf-8',errors='replace'))
    # The Python installation ships its runtime license, including incorporated libraries.
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():sections.append('\n--- CPython ---\n'+python_license.read_text(encoding='utf-8',errors='replace'))
    for folder in ('tcl8.6','tk8.6'):
        license_path=Path(sys.base_prefix)/'tcl'/folder/'license.terms'
        if license_path.exists():sections.append('\n--- '+folder+' ---\n'+license_path.read_text(errors='replace'))
    sections.append('\n--- pySerial 3.5 ---\n'+(root/'LICENSES/pySerial-BSD.txt').read_text(encoding='utf-8'))
    lgpl=root/'LICENSES/libusb-LGPL-2.1.txt'
    if not lgpl.exists():raise FileNotFoundError('Add the exact libusb 1.0.26 COPYING to '+str(lgpl))
    sections.append('\n--- libusb 1.0.26 ---\n'+lgpl.read_text(encoding='utf-8'))
    target=out/'WINDOWS-NOTICES.txt';target.write_text('\n'.join(sections),encoding='utf-8');return target

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('dist/windows'));p.add_argument('--work',type=Path,default=Path('build/windows'))
    args=p.parse_args()
    if os.name!='nt':raise SystemExit('Build this executable on Windows x64')
    root=Path(__file__).resolve().parents[1];out=args.output.resolve();work=args.work.resolve()
    out.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    notice=notices(root,work)
    name='A523-Debian-Flasher-v0.2.0-Windows-x64'
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed','--noupx','--uac-admin',
        '--name',name,'--icon',str(root/'packaging/flasher.ico'),'--distpath',str(out),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),
        '--paths',str(root),'--collect-all','libusb_package','--collect-all','importlib_resources',
        '--hidden-import','usb.backend.libusb1','--hidden-import','serial.tools.list_ports_windows',
        '--add-data',str(root/'board/release-manifest.json')+':board',
        '--add-data',str(root/'packaging/flasher.ico')+':packaging',
        '--add-data',str(notice)+':.','--add-data',str(root/'LICENSES')+':LICENSES',
        str(root/'flash_gui.py')]
    subprocess.run(command,cwd=root,check=True)
    exe=out/(name+'.exe');checksum=hashlib.sha256(exe.read_bytes()).hexdigest()
    report=dict(tool='v0.2.0',image='v0.1.0-20261114',exe=exe.name,bytes=exe.stat().st_size,sha256=checksum,
        dependencies={n:importlib.metadata.version(n) for n in ('pyusb','pyserial','libusb-package','importlib_resources','pyinstaller','pyinstaller-hooks-contrib')},
        python=sys.version,architecture='Windows x64',code_signed=False)
    (out/'windows-build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (out/'WINDOWS-NOTICES.txt').write_bytes(notice.read_bytes())
    print('WINDOWS_EXE_BUILT',json.dumps(report),flush=True)

if __name__=='__main__':main()
