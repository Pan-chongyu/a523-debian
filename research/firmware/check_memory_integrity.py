import ctypes,hashlib,json,mmap,os,signal,time
from pathlib import Path
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        args=(p/'cmdline').read_bytes().split(b'\0')
        if args and (args[0].endswith(b'/glmark2-es2') or b'/home/debian/verify_gpu_workload_extended.py' in args):
            os.kill(int(p.name),signal.SIGTERM)
            print('STOPPED_GPU_TEST_PID',p.name,flush=True)
    except (ProcessLookupError,PermissionError,FileNotFoundError):pass
for name in ['/usr/lib/aarch64-linux-gnu/libmount.so.1.1.0','/home/debian/tzx_power_key.ko']:
    p=Path(name)
    if not p.exists():continue
    normal=p.read_bytes()
    rows={'file':name,'bytes':len(normal),'sha256_normal':hashlib.sha256(normal).hexdigest(),'md5_normal':hashlib.md5(normal).hexdigest()}
    try:
        fd=os.open(p,os.O_RDONLY|os.O_DIRECT)
        mem=mmap.mmap(-1,(len(normal)+4095)//4096*4096)
        size=os.readv(fd,[mem]);os.close(fd)
        direct=mem[:size];mem.close()
        rows.update({'bytes_direct':size,'sha256_direct':hashlib.sha256(direct).hexdigest(),'md5_direct':hashlib.md5(direct).hexdigest(),'same_direct':direct==normal})
    except OSError as e:rows['direct_error']=str(e)
    print(json.dumps(rows),flush=True)
print('EXPECTED_LIBMOUNT_MD5',Path('/var/lib/dpkg/info/libmount1:arm64.md5sums').read_text(),flush=True)
print('CPU_BOOT',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),flush=True)
