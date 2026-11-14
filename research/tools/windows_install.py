"""Install fresh Debian only to the exact TZX USB-exported eMMC user area.

Requires the exact USB disk, verified by Windows metadata and handle IOCTLs.
Removable disks which Windows cannot offline must have no partition table.
Writes the root/boot filesystems first, then the new boot chain and GPT.
"""
import argparse
import ctypes
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
from fel_device import ROOT, CAPACITY, EXPECTED_CID

parser = argparse.ArgumentParser()
parser.add_argument("--disk", type=int, required=True)
parser.add_argument("--probe-write", action="store_true")
args = parser.parse_args()
assert args.disk > 0
cmd = (f"$d=Get-Disk -Number {args.disk}; $c=Get-CimInstance Win32_DiskDrive -Filter 'Index={args.disk}'; "
       "@{Number=$d.Number;Size=$d.Size;BusType=[string]$d.BusType;IsBoot=$d.IsBoot;IsSystem=$d.IsSystem;"
       "IsOffline=$d.IsOffline;PartitionStyle=[string]$d.PartitionStyle;NumberOfPartitions=$d.NumberOfPartitions;"
       "Partitions=@(Get-Partition -DiskNumber $d.Number -ErrorAction SilentlyContinue | ForEach-Object {"
       "@{Offset=$_.Offset;Size=$_.Size;DriveLetter=[string]$_.DriveLetter}});"
       "SerialNumber=$d.SerialNumber;PNPDeviceID=$c.PNPDeviceID;Model=$c.Model} | ConvertTo-Json -Compress -Depth 4")
meta = json.loads(subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", cmd], text=True))
assert meta["Size"] == CAPACITY * 512 and meta["BusType"] == "USB"
assert not meta["IsBoot"] and not meta["IsSystem"]
assert "TZX-A523-20261109" in meta["PNPDeviceID"] and meta["PNPDeviceID"].startswith("USBSTOR\\")
erase = (ROOT / "evidence/emmc-erase.txt").read_text()
assert "USER_AREA_DISCARD_COMPLETE" in erase and "ERASE_RC:0" in erase
layout = json.loads((ROOT / "build/install-layout.json").read_text())
assert layout["cid"] == EXPECTED_CID and layout["sectors"] == CAPACITY

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.DeviceIoControl.argtypes = [w.HANDLE,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD),ctypes.c_void_p]
k.DeviceIoControl.restype = w.BOOL
k.SetFilePointerEx.argtypes = [w.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), w.DWORD]
k.SetFilePointerEx.restype = w.BOOL
k.ReadFile.argtypes = [w.HANDLE,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD),ctypes.c_void_p]
k.WriteFile.argtypes = k.ReadFile.argtypes
k.ReadFile.restype = k.WriteFile.restype = w.BOOL
k.FlushFileBuffers.argtypes = [w.HANDLE]
k.CloseHandle.argtypes = [w.HANDLE]

def checked(ok):
    if not ok: raise ctypes.WinError(ctypes.get_last_error())

volume_handles = []
if not meta["IsOffline"]:
    # Windows represents a blank removable medium as a full-disk volume.
    # Lock that exact volume and dismount it before opening the physical disk.
    partitions = meta["Partitions"]
    assert len(partitions) == 1
    part = partitions[0]
    assert part["Offset"] == 0 and part["Size"] == CAPACITY * 512
    letter = part["DriveLetter"]
    assert len(letter) == 1 and "A" <= letter <= "Z" and letter != "C"
    vh = k.CreateFileW(r"\\.\{}:".format(letter), 0xC0000000, 3, None, 3, 0, None)
    if vh == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    b=ctypes.create_string_buffer(12);done=w.DWORD()
    checked(k.DeviceIoControl(vh,0x2D1080,None,0,b,12,ctypes.byref(done),None))
    assert struct.unpack("<III",b.raw)[1] == args.disk
    checked(k.DeviceIoControl(vh,0x90018,None,0,None,0,ctypes.byref(done),None))
    checked(k.DeviceIoControl(vh,0x90020,None,0,None,0,ctypes.byref(done),None))
    volume_handles.append(vh)

handle = k.CreateFileW(r"\\.\PhysicalDrive" + str(args.disk), 0xC0000000, 3, None, 3, 0x80000000, None)
if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
report = {"windows_disk": meta, "cid_verified_on_tablet": EXPECTED_CID, "writes": []}
path = ROOT / "evidence/debian-install.json"
def save(): path.write_text(json.dumps(report, indent=2), encoding="utf-8")
def ioctl(code, length):
    b=ctypes.create_string_buffer(length); done=w.DWORD()
    checked(k.DeviceIoControl(handle,code,None,0,b,length,ctypes.byref(done),None)); return b.raw[:done.value]
def seek(offset): checked(k.SetFilePointerEx(handle,offset,None,0))
def read(length):
    b=ctypes.create_string_buffer(length);done=w.DWORD();checked(k.ReadFile(handle,b,length,ctypes.byref(done),None))
    if done.value != length: raise IOError("Short raw disk read")
    return b.raw
def write(data):
    done=w.DWORD();b=ctypes.create_string_buffer(data);checked(k.WriteFile(handle,b,len(data),ctypes.byref(done),None))
    if done.value != len(data): raise IOError("Short raw disk write")
def flash(name, lba):
    source=ROOT/"build"/name;size=source.stat().st_size
    assert size % 512 == 0 and (lba * 512 + size) <= CAPACITY * 512
    item={"file":name,"lba":lba,"bytes":size,"written":0};report["writes"].append(item);save()
    sha=hashlib.sha256();seek(lba*512);last=time.monotonic()
    with source.open("rb") as f:
        while chunk:=f.read(64*1024):
            write(chunk);sha.update(chunk);item["written"]+=len(chunk)
            if time.monotonic()-last>=10:
                print(f'{name}: written {item["written"]}/{size}',flush=True);save();last=time.monotonic()
    checked(k.FlushFileBuffers(handle));item["sha256"]=sha.hexdigest();save()
    seek(lba*512);back=hashlib.sha256();remaining=size;last=time.monotonic()
    while remaining:
        n=min(64*1024,remaining);back.update(read(n));remaining-=n
        if time.monotonic()-last>=10:
            print(f'{name}: verified {size-remaining}/{size}',flush=True);last=time.monotonic()
    if back.digest()!=sha.digest(): raise IOError("Full disk readback hash mismatch: "+name)
    item["readback"]="PASS";save();print(f'{name}: complete SHA256 readback PASS',flush=True)

try:
    assert struct.unpack("<q",ioctl(0x7405C,8))[0]==CAPACITY*512
    dtype,number,partition=struct.unpack("<III",ioctl(0x2D1080,12))
    assert dtype==7 and number==args.disk
    seek(0)
    assert not any(read(1024)), "Installation requires the already erased MBR/GPT header"
    save()
    if args.probe_write:
        with (ROOT/"build/debian-rootfs.ext4").open("rb") as source:
            test_data=source.read(65536)
        seek(1179648*512);write(test_data);checked(k.FlushFileBuffers(handle));seek(1179648*512)
        assert read(len(test_data))==test_data
        report["status"]="64K_RAW_USB_WRITE_READBACK_PASS"
    else:
        flash("debian-rootfs.ext4",1179648)
        flash("debian-boot.fat",131072)
        flash("linux-bundle.bin",4096)
        flash("chain-loader.toc0",256)
        flash("gpt-backup.bin",CAPACITY-33)
        flash("gpt-primary.bin",0)
        report["status"]="FRESH_DEBIAN_FULL_READBACK_VERIFIED_UNBOOTED"
except Exception as error:
    report["error"]=repr(error);raise
finally:
    k.CloseHandle(handle)
    for vh in volume_handles: k.CloseHandle(vh)
    save();print(json.dumps(report,indent=2),flush=True)
