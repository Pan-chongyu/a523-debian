"""Add only the boot-time VPU IOMMU provider to the proven board DTB."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/extended-kernel'
DT=OUT/'board.dtb'
shutil.copyfile(ROOT/'build/screen-boot-kernel/board.dtb',DT)
def get(node,prop,kind='x'):
    return subprocess.check_output(['fdtget','-t',kind,str(DT),node,prop],text=True).strip()
def nodes(node='/'):
    result=[node]
    for child in subprocess.check_output(['fdtget','-l',str(DT),node],text=True).split():
        result+=nodes(node.rstrip('/')+'/'+child)
    return result
for node in nodes():
    props=subprocess.check_output(['fdtget','-p',str(DT),node],text=True).split()
    if 'phandle' in props: assert get(node,'phandle')!='90'
assert get('/soc','\u0023address-cells')==get('/soc','\u0023size-cells')=='1'
assert get('/soc/clock-controller@2001000','phandle')=='2'
assert get('/soc/power-controller@7060000','phandle')=='3'
node='/soc/iommu@2010000'
subprocess.run(['fdtput','-c',str(DT),node],check=True)
def put(prop,values,kind='x'):
    subprocess.run(['fdtput','-t',kind,str(DT),node,prop,*values.split()],check=True)
put('compatible','allwinner,sun55i-a523-iommu allwinner,sun50i-h616-iommu','s')
put('reg','2010000 1000');put('interrupts','0 41 4')
put('clocks','2 48');put('resets','2 4e');put('#iommu-cells','1');put('phandle','90')
put('status','okay','s')
subprocess.run(['dtc','-I','dtb','-O','dts',str(DT),'-o',str(OUT/'board.dts')],check=True,stderr=subprocess.DEVNULL)
assert b'\x00\x00\x00\x90' in DT.read_bytes()
assert get(node,'clocks')=='2 48' and get(node,'resets')=='2 4e'
print('ADDED_ONLY_VPU_IOMMU_PROVIDER',hashlib.sha256(DT.read_bytes()).hexdigest())
