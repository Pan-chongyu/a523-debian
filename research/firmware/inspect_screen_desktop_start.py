"""Read desktop/session timing without restarting any service."""
import json
from pathlib import Path
import subprocess

out={}
for name,args in (
    ('lightdm_journal',['journalctl','-b','-o','short-monotonic','--no-pager','-u','lightdm','-u','user@1000']),
    ('lightdm_chain',['systemd-analyze','critical-chain','lightdm.service']),
    ('desktop_processes',['ps','-eo','pid,ppid,lstart,etimes,args']),
    ('user_services',['runuser','-u','debian','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','list-units','--all','--no-pager'])):
    result=subprocess.run(args,text=True,capture_output=True,timeout=25)
    text=result.stdout+result.stderr
    if name=='desktop_processes':
        text='\n'.join(line for line in text.splitlines() if any(s in line.lower() for s in
            ('xfce','xorg','lightdm','at-spi','onboard','dbus','screen','nm-applet','pulseaudio')))
    out[name]=text
paths=[Path('/var/log/lightdm/lightdm.log'),Path('/home/debian/.xsession-errors'),
       Path('/etc/xdg/xfce4/xinitrc'),Path('/home/debian/.xsessionrc'),Path('/home/debian/.xprofile')]
paths+=list(Path('/home/debian/.config/autostart').glob('*.desktop'))
paths+=list(Path('/etc/xdg/autostart').glob('*tzx*'))
out['files']={str(p):p.read_text(errors='replace')[-18000:] for p in paths if p.is_file()}
out['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps(out,indent=2))
