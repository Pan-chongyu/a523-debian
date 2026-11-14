"""Qualify the actual compact boot, unchanged acceleration and mixed load."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

assert os.geteuid()==0
state=Path('/var/lib/tzx')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
installed=json.loads((state/'boot-compact-v2-installed.json').read_text())
assert installed['state']=='installed' and boot!=installed['installed_boot_id']
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=150)
print(run('python3','/home/debian/install_boot_compact.py','verify'),end='',flush=True)
print(run('python3','/home/debian/verify_boot_streamline.py'),end='',flush=True)
manifest=json.loads(Path('/usr/local/lib/tzx-boot-compact-v2/bundle-manifest.json').read_text())
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x2d000) as view:
        values=struct.unpack_from('<3Ii4I4Q2IQ',view,0x800)
finally:os.close(fd)
names=('magic','version','phase','error','raw_bytes','packed_bytes','esr','crc32',
       'entered_ticks','relocated_ticks','decoded_ticks','checked_ticks','counter_hz','reserved','exception_pc')
receipt=dict(zip(names,values))
assert [receipt[k] for k in ('magic','version','phase','error')]==[0xa523c701,1,4,0]
assert receipt['raw_bytes']==manifest['kernel_decoded_bytes'] and receipt['packed_bytes']+32==manifest['items'][0]['bytes']
assert receipt['crc32']==manifest['native_kernel_output_CRC32'] and receipt['esr']==receipt['exception_pc']==0
assert receipt['counter_hz']==24000000
assert receipt['reserved']==3, 'The output was cleaned to PoC and MMU/data cache were disabled'
assert 0<receipt['entered_ticks']<receipt['relocated_ticks']<receipt['decoded_ticks']<receipt['checked_ticks']
cmdline=Path('/proc/cmdline').read_text().strip()
assert 'earlycon=' not in cmdline and 'ignore_loglevel' not in cmdline and 'ttyS0' not in cmdline
assert 'console=tty0' in cmdline and 'quiet' in cmdline
parent=json.loads((state/'boot-streamline-qualified.json').read_text())
assert parent['boot_id']==boot and parent['status']=='PASS'
profile=json.loads(run('python3','/home/debian/inspect_boot_logo_speed.py'))
p=profile['profile_receipt'];assert p[:2]==[0xa523f101,1]
assert p[7]==p[8]==manifest['new_read_bytes']//512+1
receipt.update(relocate_s=(values[9]-values[8])/24000000,
               decode_s=(values[10]-values[9])/24000000,
               decoded_crc_s=(values[11]-values[10])/24000000,
               total_s=(values[11]-values[8])/24000000)
result=dict(status='PASS',profile=manifest['profile'],boot_id=boot,captured_unix=int(time.time()),
    parent_startup=parent,compact_receipt=receipt,cmdline=cmdline,
    original_kernel_sha256=hashlib.sha256(Path('/boot/Image').read_bytes()).hexdigest(),
    read_bytes=manifest['new_read_bytes'],old_read_bytes=manifest['old_read_bytes'],
    loader_read_s=p[4]/24000000,loader_crc_s=p[5]/24000000,
    loader_last_counter_s=p[6]/24000000,linux_entry_counter_s=values[8]/24000000,
    kernel_branch_counter_s=values[11]/24000000,
    desktop_last_process_kernel_s=parent['desktop']['last_desktop_process_start_kernel_s'],
    first_image_counter_s=parent['first_image_counter_s'],physical_power_key_test=False,
    visual_confirmation='pending',measurement_scope='counter receipts and Linux process creation, not a physical stopwatch')
assert result['original_kernel_sha256']==manifest['kernel_decoded_sha256']
assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
encoded=json.dumps(result,indent=2)+'\n'
(state/('boot-compact-qualified-'+boot+'.json')).write_text(encoded)
(state/'boot-compact-qualified.json').write_text(encoded)
print('BOOT_COMPACT_ACTUAL_REBOOT_FULL_STACK_AND_MIXED_LOAD_PASS',json.dumps({k:result[k] for k in (
    'boot_id','first_image_counter_s','loader_read_s','loader_crc_s','kernel_branch_counter_s',
    'desktop_last_process_kernel_s')}),json.dumps(receipt),flush=True)
