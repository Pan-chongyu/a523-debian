"""Compare identical browser launches with cold versus preloaded app file pages.

Only clean pages of three named Firefox files are evicted, with no global cache
drop. Refuse to evict while a user's browser process is running.
"""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import time
assert os.geteuid()==0
files=[Path('/usr/lib/firefox-esr')/name for name in ('libxul.so','omni.ja','browser/omni.ja')]
for proc in Path('/proc').glob('[0-9]*'):
    try:assert (proc/'comm').read_text().strip() not in ('firefox-esr','x-www-browser','firefox'),'User browser is running; do not evict its files'
    except FileNotFoundError:pass
libc=C.CDLL(None,use_errno=True)
libc.mmap.argtypes=[C.c_void_p,C.c_size_t,C.c_int,C.c_int,C.c_int,C.c_long];libc.mmap.restype=C.c_void_p
libc.mincore.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p]
libc.munmap.argtypes=[C.c_void_p,C.c_size_t]
def residency(path):
    size=path.stat().st_size;pages=(size+4095)//4096
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
    try:
        mapping=libc.mmap(None,size,1,2,fd,0);assert mapping!=C.c_void_p(-1).value
        try:
            result=(C.c_ubyte*pages)();assert libc.mincore(mapping,size,result)==0
            return dict(pages=pages,resident_pages=sum(v&1 for v in result))
        finally:libc.munmap(mapping,size)
    finally:os.close(fd)
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
policies=[Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0,4)]
assert all((p/'scaling_governor').read_text().strip()=='performance' for p in policies)
record={'boot_id':boot,'cache_scope':'three Firefox files only; no drop_caches','same_launch_parameters':True,
    'cpu_governor_in_both_phases':'performance','phases':[]}
for mode in ('cold','preloaded'):
    for path in files:
        fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
        try:os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
        finally:os.close(fd)
    cold={str(path):residency(path) for path in files}
    assert all(v['resident_pages']<.05*v['pages'] for v in cold.values()),cold
    preload_seconds=0
    if mode=='preloaded':
        started=time.monotonic()
        for path in files:
            with path.open('rb',buffering=0) as stream:
                while stream.read(1024*1024):time.sleep(.004)
        preload_seconds=round(time.monotonic()-started,3)
    before_launch={str(path):residency(path) for path in files}
    if mode=='preloaded':assert all(v['resident_pages']==v['pages'] for v in before_launch.values())
    label='controlled-cache-'+mode+'-'+boot[:8]
    log=Path('/home/debian/app-launch-profile')/(label+'.log')
    with log.open('w') as stream:
        subprocess.run(['python3','/home/debian/profile_app_launch.py','--label',label,'--apps','browser','--rounds','1'],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=60)
    launch=json.loads(log.with_suffix('.json').read_text())
    assert not launch['boost_requested'] and not launch['browser_binary_disk_cache']
    assert all(p['scaling_governor']=='performance' for p in launch['policy'])
    record['phases'].append(dict(mode=mode,after_eviction=cold,before_launch=before_launch,
        background_preload_seconds=preload_seconds,launch=launch['samples'][0]))
cold,warm=record['phases']
ratio=warm['launch']['window_visible_seconds']/cold['launch']['window_visible_seconds']
assert cold['launch']['storage_read_bytes']>100*1024*1024
assert warm['launch']['storage_read_bytes']<30*1024*1024
assert ratio<.9,ratio
record['status']='PASS';record['preloaded_to_cold_seconds_ratio']=ratio
Path('/var/lib/tzx/app-cache-comparison-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
print('CONTROLLED_SAME_BROWSER_PRELOAD_COMPARISON_PASS',json.dumps(dict(boot_id=boot,
    cold_seconds=cold['launch']['window_visible_seconds'],preloaded_seconds=warm['launch']['window_visible_seconds'],
    cold_storage_bytes=cold['launch']['storage_read_bytes'],preloaded_storage_bytes=warm['launch']['storage_read_bytes'],
    background_preload_seconds=warm['background_preload_seconds'],ratio=ratio)),flush=True)
