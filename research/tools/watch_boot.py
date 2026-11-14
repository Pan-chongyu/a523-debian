"""Wait for SSH or capture the reserved boot markers after a FEL fallback."""
import argparse,json,socket,struct,time,subprocess,sys,re
from fel_device import ROOT,Device,libusb_package
from serial.tools import list_ports

p=argparse.ArgumentParser()
p.add_argument('--output',default='watched-boot.json')
p.add_argument('--seconds',type=int,default=180)
p.add_argument('--previous-boot-id',help='Require a different Linux boot ID before declaring success')
a=p.parse_args()
until=time.monotonic()+a.seconds
result={'state':'TIMEOUT'}
host_network=None
next_network_check=0
last_ssh=None
next_ssh_check=0
while time.monotonic()<until:
    ports=[p for p in list_ports.comports() if p.vid==0x1d6b and p.pid==0x0104
           and p.serial_number=='TZX-A523-20261109']
    if ports and time.monotonic()>=next_network_check:
        network=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
            str(ROOT/'tools/ensure_usb_network.ps1'),'-Configure'],stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,timeout=30)
        try:host_network=json.loads(network.stdout.decode('utf-8-sig'))
        except (ValueError,UnicodeError):host_network={'error':'Unable to read host USB network state'}
        next_network_check=time.monotonic()+30
    try:
        with socket.create_connection(('192.168.77.2',22),timeout=1) as s:
            if s.recv(200).startswith(b'SSH-2.0-OpenSSH'):
                if time.monotonic()<next_ssh_check:
                    time.sleep(2)
                    continue
                next_ssh_check=time.monotonic()+5
                check=subprocess.run([sys.executable,str(ROOT/'tools/tablet_ssh.py'),
                    '--command','cat /proc/sys/kernel/random/boot_id; uname -a; cat /proc/uptime'],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
                output=check.stdout.decode(errors='replace')
                boot_id=output.splitlines()[0] if output else ''
                if check.returncode==0 and re.fullmatch(r'[0-9a-f-]{36}',boot_id):
                    last_ssh={'linux_boot_id':boot_id,'linux_identity':output}
                    if boot_id!=a.previous_boot_id:
                        result={'state':'SSH_READY',**last_ssh,
                                'usb_serial_ports':[p.device for p in ports],'host_network':host_network};break
    except OSError:pass
    except subprocess.TimeoutExpired:pass
    if libusb_package.find(idVendor=0x1f3a,idProduct=0xefe8):
        d=Device(timeout=2000)
        try:
            d.connect()
            result={'state':'FEL_RETURNED','rtc_gp':[f'0x{x:08x}' for x in
                    struct.unpack('<8I',d._read_raw(0x07090100,32))]}
            break
        finally:d.close()
    time.sleep(2)
if result['state']=='TIMEOUT':
    ports=[p for p in list_ports.comports() if p.vid==0x1d6b and p.pid==0x0104
           and p.serial_number=='TZX-A523-20261109']
    result.update(usb_serial_ports=[p.device for p in ports],host_network=host_network)
    if last_ssh:
        result.update(state='SSH_READY_BOOT_UNCHANGED',**last_ssh)
    elif ports:result['state']='USB_PRESENT_SSH_UNREACHABLE'
(ROOT/'evidence'/a.output).write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2),flush=True)
raise SystemExit(0 if result['state']=='SSH_READY' else 2)
