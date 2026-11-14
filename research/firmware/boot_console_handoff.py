"""Validate the live SRAM display and retain it for native DRM adoption."""
import hashlib,json,mmap,os,struct,subprocess,time
from pathlib import Path
assert os.geteuid()==0
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert not Path('/sys/module/tzx_display').exists()
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC);maps={}
def get(a):
    base=a&~4095
    if base not in maps:maps[base]=mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=base)
    return struct.unpack_from('<I',maps[base],a&4095)[0]
try:
    raw=b''.join(struct.pack('<I',get(0x2d200+i*4)) for i in range(104))
    magic,version,stage,active,pmic_original,count,entered,lit,panel_id,status,phy,before,after=struct.unpack_from('<6IQQ5I',raw)
    assert (magic,version,stage,active,count,panel_id)==(0xa523ed01,2,0x100,1,20,0x936504)
    assert status&16 and before!=after and pmic_original in (0xd5,0xd7)
    logo_raw=b''.join(struct.pack('<I',get(0x2d600+i*4)) for i in range(26))
    values=struct.unpack('<8I3Q12I',logo_raw)
    names=('magic','version','stage','active','error','sectors','crc','bytes','entered_ticks','loaded_ticks','lit_ticks',
           'de_clock','de_bgr','top_route','tcon_source','dsi_jump','de_version','rcq_status','ovl_address',
           'line_before','line_after','pixel_count','reserved')
    logo=dict(zip(names,values))
    assert values[:5]==(0xa523b001,1,0x100,1,0) and logo['ovl_address']==0x42400000
    assert logo['pixel_count']==1024000 and logo['de_version']==0x03500200
    assert get(0x05502040)&0x80000007==0x80000000 and get(0x055082f8)==0xff
    assert get(0x05000000+0x1c1010)==0x42400000 and get(0x02000c80)&1
    assert int(subprocess.check_output(['i2cget','-y','0','0x34','0x91'],text=True),16)==pmic_original|8
    line=get(0x055082e0);time.sleep(.035);assert line!=get(0x055082e0)
    # Claim the live domains before an unowned-provider power-off can discard
    # the SRAM-programmed DSI/TCON state. Native consumers attach immediately.
    if not Path('/sys/module/sun55i_pck600').exists():
        subprocess.run(['insmod','/usr/local/lib/tzx-boot-console/sun55i-pck600.ko'],check=True,timeout=5)
    subprocess.run(['modprobe','tzx_display_domains'],check=True,timeout=5)
    assert get(0x05502040)&0x80000007==0x80000000 and get(0x055082f8)==0xff
    assert all(get(a)&15==8 for a in (0x07063008,0x07064008,0x07065008))
    logo.update(boot_id=boot,lit_counter_s=logo['lit_ticks']/24000000,
        handoff_result='live panel retained for native DRM adoption',receipt_raw_hex=logo_raw.hex(),
        handoff_monotonic_s=time.monotonic())
    panel=dict(boot_id=boot,magic=hex(magic),version=version,stage=hex(stage),active_on_entry=True,
        pmic_original=hex(pmic_original),panel_id=hex(panel_id),panel_status=hex(status),
        line_before=before,line_after=after,lit_counter_s=lit/24000000,
        entered_counter_s=entered/24000000,receipt_raw_hex=raw.hex(),boot_logo=logo,
        result='live-preview-retained-for-native-input-and-display',handoff_monotonic_s=time.monotonic())
    for name,obj in (('boot-panel-stage.json',panel),('boot-logo-stage.json',logo)):
        Path('/var/lib/tzx',name).write_text(json.dumps(obj,indent=2)+'\n')
    Path('/run/tzx-boot-console-adopt.json').write_text(json.dumps(dict(boot_id=boot,adopt=True,
        live_PWM_preserved=True,live_DSI_preserved=True,panel_rail_preserved=True,logo=logo),indent=2)+'\n')
    print('BOOT_CONSOLE_LIVE_PANEL_RETAINED',boot,flush=True)
finally:
    for v in maps.values():v.close()
    os.close(fd)
