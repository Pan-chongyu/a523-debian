"""Verify a real changed boot, the actual splash framebuffer and native desktop."""
import hashlib,json,mmap,os,struct,subprocess,time
from pathlib import Path
assert os.geteuid()==0
state=Path('/var/lib/tzx');installed=json.loads((state/'boot-logo-installed.json').read_text())
m=json.loads(Path('/home/debian/boot-logo/loader.toc0.json').read_text())
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot!=installed['installed_boot_id']
assert installed['toc0_sha256']==m['image_sha256']
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=75)
print(run('python3','/home/debian/install_boot_logo.py','verify',installed['toc0_sha256']),end='',flush=True)
logo=json.loads((state/'boot-logo-stage.json').read_text())
assert logo['boot_id']==boot and (logo['magic'],logo['version'],logo['stage'],logo['active'],logo['error'])==(0xa523b001,1,0x100,1,0)
assert logo['sectors']*512==logo['bytes']==m['payload_bytes'] and logo['crc']==m['payload_crc32']
assert logo['ovl_address']==0x42400000 and logo['pixel_count']==1024000 and logo['de_version']==0x03500200
assert logo['rcq_status']&4 and logo['line_before']!=logo['line_after']
assert logo['entered_ticks']<logo['loaded_ticks']<logo['lit_ticks']
assert logo['handoff_result']=='DE stopped and original reset/gate restored'
assert Path('/proc/device-tree/reserved-memory/boot-splash@42000000/reg').read_bytes()==struct.pack('>4I',0,0x42000000,0,0x900000)
assert Path('/proc/device-tree/reserved-memory/boot-splash@42000000/no-map').exists()
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
try:
    with mmap.mmap(fd,4096000,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x42400000) as view:
        pixel_hash=hashlib.sha256(view).hexdigest()
    with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x2d000) as view:
        cpu=struct.unpack_from('<16I2Q',view,0x500)
        assert struct.unpack_from('<I',view,0x60c)[0]==0, 'Firmware DE ownership must be released'
finally:os.close(fd)
assert pixel_hash==m['native_bgra_sha256']
assert cpu[:4]==(0xa523cf01,1,4,0) and cpu[8:10]==(1416000,1150)
assert cpu[4:7]==cpu[10:13] and cpu[13]==0 and cpu[14]==0x54000 and cpu[17]>cpu[16]
assert hashlib.sha256(Path('/boot/Image').read_bytes()).hexdigest()=='470dd0c350c7ef7aad392eac3a35237672862f0fffdacea8da4e6adb6740e6e4'
for attempt in range(100):
    health=json.loads((state/'screen-boot-health.json').read_text())
    if health.get('boot_id')==boot and health.get('result')=='PASS':break
    time.sleep(.5)
else:raise AssertionError('Native screen health did not complete')
assert 'current 1280 x 800' in health['xrandr'] and ' right ' in health['xrandr']
assert health['display_setup']['fbcon_rotate']=='1'
assert '0.000000, 1.000000, 0.000000, -1.000000, 0.000000, 1.000000' in health['display_setup']['touch_properties']
units=('tzx-display','tzx-touch','tzx-gpu','tzx-cpu-dvfs','tzx-gpu-performance','tzx-emmc-hs',
       'tzx-screen-health','tzx-dram-gpu-health','tzx-video','tzx-zram','tzx-wifi','tzx-bluetooth','tzx-audio','lightdm')
assert run('systemctl','is-active',*units).split()==['active']*len(units)
assert not run('systemctl','--failed','--no-legend','--plain').strip()
for name in ('screen_buffer_errors','screen_panel_errors'):assert int(Path('/sys/module/tzx_display/parameters',name).read_text())==0
gpu=json.loads((state/'dram-gpu-boot-health.json').read_text());assert gpu['boot_id']==boot and gpu['status']=='PASS'
mode=json.loads(Path('/run/tzx-performance-mode.json').read_text());assert mode['boot_id']==boot and mode['state']=='active'
assert mode['governors']==['performance','performance']
record=dict(status='PASS',boot_id=boot,toc0_sha256=m['image_sha256'],
    logo=logo,retained_splash_pixel_sha256=pixel_hash,original_CPUA_voltage_restored_before_TFA=True,
    actual_source_png_sha256=m['source_sha256'],orientation='right',native_desktop_and_touch_matrix='PASS',
    source_lossless_after_resize=True,performance_mode=mode,failed_services=[],visual_confirmation='pending')
installed.update(state='actual-reboot-verified',verified_boot_id=boot,actual_boot_verification='PASS')
(state/'boot-logo-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
(state/'boot-logo-installed.json').write_text(json.dumps(installed,indent=2)+'\n')
panel=json.loads((state/'boot-panel-installed.json').read_text());panel.update(state='actual-normal-reboot-verified',verified_boot_id=boot)
(state/'boot-panel-installed.json').write_text(json.dumps(panel,indent=2)+'\n')
print('BOOT_LOGO_ACTUAL_FIRMWARE_FRAMEBUFFER_AND_NATIVE_HANDOFF_PASS',json.dumps(record),flush=True)
