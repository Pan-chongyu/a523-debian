"""Read the actual SRAM frequency/voltage receipt and verify the real boot."""
import json,mmap,os,struct,subprocess
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state=Path('/var/lib/tzx');installed=json.loads((state/'boot-cpu-performance-installed.json').read_text())
assert installed['installed_boot_id']!=boot and installed['state']=='installed'
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    with mmap.mmap(fd,4096,prot=mmap.PROT_READ,offset=0x2d000) as view:
        fields=[struct.unpack_from('<I',view,offset)[0] for offset in range(0x500,0x550,4)]
finally:os.close(fd)
names=('magic','version','stage','active','initial_pll','initial_mux','initial_voltage_selector','SID_word',
    'peak_khz','peak_mv','final_pll','final_mux','final_voltage_selector','error','arm64_address','reserved')
receipt=dict(zip(names,fields[:16]))
receipt.update(boost_ticks=fields[16]|fields[17]<<32,restore_ticks=fields[18]|fields[19]<<32)
print('SRAM_CPU_PERFORMANCE_RAW_RECEIPT',json.dumps(receipt),flush=True)
assert fields[:4]==[0xa523cf01,1,4,0],receipt
assert receipt['SID_word']==0x48 and receipt['peak_khz']==1416000 and receipt['peak_mv']==1150
assert receipt['initial_voltage_selector']==receipt['final_voltage_selector']
assert receipt['final_voltage_selector']&127==40
assert receipt['initial_mux']==receipt['final_mux']
assert receipt['initial_pll']==receipt['final_pll'],receipt
assert receipt['error']==0 and receipt['arm64_address']==0x54000
assert receipt['restore_ticks']>receipt['boost_ticks']
result=subprocess.check_output(['python3','/home/debian/install_boot_cpu_performance.py','verify',installed['toc0_sha256']],text=True,timeout=50)
print(result,end='',flush=True)
profile=subprocess.check_output(['python3','/home/debian/read_boot_profile.py'],text=True,timeout=25)
print(profile,end='',flush=True)
record=dict(status='PASS',boot_id=boot,receipt=receipt,
    boosted_seconds=(receipt['restore_ticks']-receipt['boost_ticks'])/24000000,
    original_480MHz_900mV_restored_before_TFA=True,full_original_panel_and_payload_CRC_retained=True,
    toc0_sha256=installed['toc0_sha256'],full_profile_output=profile)
(state/'boot-cpu-performance-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
installed.update(actual_boot_verification='PASS',verified_boot_id=boot)
(state/'boot-cpu-performance-installed.json').write_text(json.dumps(installed,indent=2)+'\n')
print('SRAM_CPU_1416MHZ_AND_EXACT_RESTORATION_REAL_BOOT_PASS',json.dumps(record),flush=True)
