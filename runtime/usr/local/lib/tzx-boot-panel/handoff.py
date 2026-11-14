"""Release only the recorded SRAM preview resources before native touch/display."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()==Path('/etc/tzx/device-cid').read_text().strip()
assert not Path('/sys/module/tzx_touch_runtime').exists() and not Path('/sys/module/tzx_display').exists()
state=Path('/var/lib/tzx')
installed=json.loads((state/'boot-panel-installed.json').read_text())
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
fd=os.open('/dev/mmcblk0',os.O_RDONLY)
try:
    assert hashlib.sha256(os.pread(fd,49152,256*512)).hexdigest()==installed['toc0_sha256']
finally:os.close(fd)
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
maps={}
def mapping(address):
    base=address&~4095
    if base not in maps:maps[base]=mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=base)
    return maps[base]
def get(address):return struct.unpack_from('<I',mapping(address),address&4095)[0]
def put(address,value):struct.pack_into('<I',mapping(address),address&4095,value&0xffffffff)
def change(address,mask,value):put(address,(get(address)&~mask)|(value&mask))
specs=[(0x02001b28,0x8700001f),(0x02001b4c,0x20002),(0x02001b64,1<<31),
    (0x02001b70,1<<31),(0x02001b7c,0x20002),(0x02001abc,0x10001),(0x020017ac,0x10001),
    (0x02000094,0xffffff00),(0x02000098,0xff00ffff),(0x020000a0,0xc00000),
    (0x02000158,0xff00),(0x02000160,0xc0000),(0x02000c20,0xffffffff),
    (0x02000c40,0x10001),(0x02000c80,1),(0x02000d00,0xffffffff),(0x02000d04,0xffffffff),
    (0x05500004,1<<4),(0x0550000c,34),(0x05500020,1<<17)]
try:
    raw=bytes(mapping(0x2d200)[0x200:0x200+416])
    fields=struct.unpack_from('<6IQQ5I',raw)
    magic,version,stage,active,pmic_original,count,entered,lit,panel_id,panel_status,phy_debug,line_before,line_after=fields
    assert (magic,version)==(0xa523ed01,2)
    diagnostic_names=('periph_before','video_before','periph_enabled','video_enabled',
        'last_packet_type','last_packet_data','last_packet_result','last_packet_control',
        'last_rx_header','host_debug','phy_debug_after_ID','PIO_power_select','PIO_power_control',
        'PIO_power_value','PD_data','PH_data','parents_touched')
    diagnostics=dict(zip(diagnostic_names,(hex(v) for v in struct.unpack_from('<17I',raw,348))))
    assert count in (0,12,20) and active in (0,1)
    saved=[struct.unpack_from('<III',raw,60+i*12) for i in range(count)]
    assert [(a,m) for a,m,_ in saved]==specs[:count]
    record=dict(boot_id=boot,magic=hex(magic),version=version,stage=hex(stage),active_on_entry=bool(active),
        pmic_original=hex(pmic_original),saved_registers=saved,entered_counter_s=entered/24000000,
        lit_counter_s=lit/24000000 if lit else None,initializer_elapsed_s=(lit-entered)/24000000 if lit else None,
        panel_id=hex(panel_id),panel_status=hex(panel_status),phy_debug=hex(phy_debug),
        line_before=line_before,line_after=line_after,diagnostics=diagnostics,receipt_raw_hex=raw.hex())
    if active:
        assert stage==0x100 and count==20 and panel_id==0x936504 and panel_status&16
        assert line_before!=line_after and lit>entered and pmic_original in (0xd5,0xd7)
        current=int(subprocess.check_output(['i2cget','-y','0','0x34','0x91'],text=True,timeout=4),16)
        assert current==pmic_original|8
        # CCF may have gated unused boot clocks. Re-enable only these buses
        # for bounded cleanup, preserving unrelated clock/reset bits.
        for address,mask in ((0x02001b4c,0x20002),(0x02001b7c,0x20002),
                             (0x02001abc,0x10001),(0x020017ac,0x10001)):
            change(address,mask,mask)
        change(0x02000c80,1,0)
        put(0x05508010,3<<16);put(0x05502000,0);put(0x05502040,0)
        # The SRAM splash owns DE only until native input/display take over.
        # DSI/TCON and backlight are already stopped above; no DMA consumer
        # can read the reserved image while clocks/reset are restored.
        # SRAM is mapped as device memory: read aligned 32-bit words instead
        # of libc memcpy, whose short tail can use unaligned vector loads.
        logo_raw=b''.join(struct.pack('<I',get(0x2d600+4*i)) for i in range(26))
        logo_values=struct.unpack('<8I3Q12I',logo_raw)
        logo_names=('magic','version','stage','active','error','sectors','crc','bytes',
            'entered_ticks','loaded_ticks','lit_ticks','de_clock','de_bgr','top_route',
            'tcon_source','dsi_jump','de_version','rcq_status','ovl_address',
            'line_before','line_after','pixel_count','reserved')
        logo=dict(zip(logo_names,logo_values));logo['boot_id']=boot
        assert (logo['magic'],logo['version'])==(0xa523b001,1)
        assert logo['active'] in (0,1)
        if logo['active']:
            assert logo['stage']==0x100 and logo['error']==0
            assert logo['de_version']==0x03500200 and logo['ovl_address']==0x42400000
            assert logo['pixel_count']==1024000
            change(0x02001600,1<<31,1<<31);change(0x0200160c,0x10001,0x10001)
            logo['DE_domain_on_at_handoff']=(get(0x07065008)&15)==8
            if logo['DE_domain_on_at_handoff']:
                for address in (0x05008110,0x05008100,0x05008008,0x05008000):put(address,0)
            change(0x0550001c,255,logo['top_route'])
            change(0x0200160c,1<<16,0)
            time.sleep(0.00001)
            change(0x0200160c,0x10001,logo['de_bgr'])
            # Keep the registered CCF parent/divider consistent, release gate.
            change(0x02001600,1<<31,logo['de_clock'])
            put(0x2d60c,0)
            logo['handoff_result']='DE stopped and original reset/gate restored'
        else:logo['handoff_result']='optional splash failed; native display continues'
        logo.update(lit_counter_s=logo['lit_ticks']/24000000 if logo['lit_ticks'] else None,
            load_elapsed_s=(logo['loaded_ticks']-logo['entered_ticks'])/24000000 if logo['loaded_ticks'] else None,
            handoff_monotonic_s=time.monotonic(),receipt_raw_hex=logo_raw.hex())
        (state/'boot-logo-stage.json').write_text(json.dumps(logo,indent=2)+'\n')
        Path('/run/tzx-boot-logo-handoff.json').write_text(json.dumps(logo,indent=2)+'\n')
        record['boot_logo']=logo
        change(0x05509108,(1<<22)|(1<<21),0)
        change(0x05509104,(1<<20)|(1<<21)|(1<<22),0)
        for address,mask,original in reversed(saved):
            # Linux CCF already cached the firmware-selected parent/divider.
            # Release our gate but retain those fields for its clock owner.
            if address==0x02001b28:mask=1<<31
            change(address,mask,original)
        subprocess.run(['i2cset','-y','0','0x34','0x91',hex(pmic_original)],check=True,timeout=4)
        assert int(subprocess.check_output(['i2cget','-y','0','0x34','0x91'],text=True,timeout=4),16)==pmic_original
        put(0x2d20c,0)
        record['result']='early-preview-released-before-native-input-and-display'
        record['display_parent_PLL_ownership']='retained for Linux CCF; no parent PLL writes in handoff'
        record['DSI_mux_divider_ownership']='retained 150 MHz source for registered Linux CCF'
    else:
        assert stage&0xe0000000==0xe0000000
        record['result']='early-preview-failed-and-SRAM-rollback-completed; native boot continues'
    record['handoff_monotonic_s']=time.monotonic()
    (state/'boot-panel-stage.json').write_text(json.dumps(record,indent=2)+'\n')
    Path('/run/tzx-boot-panel-handoff.json').write_text(json.dumps(record,indent=2)+'\n')
    os.sync()
    print('SRAM_PANEL_PREVIEW_HANDOFF_COMPLETE',json.dumps(record),flush=True)
finally:
    for value in maps.values():value.close()
    os.close(fd)
