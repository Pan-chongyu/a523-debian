"""Extend the current full-hash guards and release the splash before Linux DE."""
import hashlib,json,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'build/boot-logo'
m=json.loads((out/'loader.toc0.json').read_text());old=m['previous_toc0_sha256'];pin=m['image_sha256']
sha=lambda b:hashlib.sha256(b).hexdigest()
files={}
with tarfile.open(root/'build/max-performance-installed-checkpoint.tar.gz') as archive:
    for short,component in (('dram','tzx-dram-gpu'),('rtc','tzx-rtc-context'),('pmic','tzx-pmic-poweroff')):
        name='usr/local/lib/'+component+'/runtime.py';before=archive.extractfile(name).read()
        needle="'"+old+"')";assert before.count(needle.encode())==1
        data=before.replace(needle.encode(),("'"+old+"', '"+pin+"')").encode())
        compile(data,name,'exec');staged=short+'-runtime.py';(out/staged).write_bytes(data)
        files['/'+name]=dict(original_sha256=sha(before),candidate_sha256=sha(data),staged_name=staged)
before=(root/'firmware/boot_panel_handoff.py').read_bytes()
assert sha(before)=='9e8af3306f46470d0e3a5ea0e73a523c13b575594df4d87723ef91efe66329d9'
text=before.decode()
needle='        change(0x05509108,(1<<22)|(1<<21),0)'
assert text.count(needle)==1
extra='''        # The SRAM splash owns DE only until native input/display take over.
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
        (state/'boot-logo-stage.json').write_text(json.dumps(logo,indent=2)+'\\n')
        Path('/run/tzx-boot-logo-handoff.json').write_text(json.dumps(logo,indent=2)+'\\n')
        record['boot_logo']=logo
'''
text=text.replace(needle,extra+needle)
compile(text,'handoff.py','exec');data=text.encode();(out/'handoff.py').write_bytes(data)
files['/usr/local/lib/tzx-boot-panel/handoff.py']=dict(original_sha256=sha(before),candidate_sha256=sha(data),staged_name='handoff.py')
(out/'guard-files.json').write_text(json.dumps(files,indent=2)+'\n')
print('BOOT_LOGO_GUARDS_AND_NATIVE_HANDOFF_PREPARED',pin,flush=True)
