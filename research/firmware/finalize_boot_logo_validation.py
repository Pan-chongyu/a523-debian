"""Qualify the current image without inheriting the old colorbar key-on timing."""
import hashlib,json,os,time
from pathlib import Path

assert os.geteuid()==0
state=Path('/var/lib/tzx');folder=Path('/home/debian/boot-logo')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
proof=json.loads((state/'boot-logo-qualified.json').read_text())
load=json.loads((state/'cpu-gpu-integration-qualified.json').read_text())
installed=json.loads((state/'boot-logo-installed.json').read_text())
manifest=json.loads((folder/'loader.toc0.json').read_text())
assert proof['boot_id']==load['boot_id']==boot
assert proof['status']==load['status']=='PASS'
assert proof['retained_splash_pixel_sha256']==manifest['native_bgra_sha256']
assert installed['state']=='actual-reboot-verified'
assert installed['toc0_sha256']==proof['toc0_sha256']==manifest['image_sha256']
assert hashlib.sha256((folder/'loader.toc0').read_bytes()).hexdigest()==manifest['image_sha256']

def atomic(path,value):
    data=(json.dumps(value,indent=2)+'\n').encode();path=Path(path)
    temp=path.with_name(path.name+'.qualified-new')
    with temp.open('wb') as stream:
        stream.write(data);os.fchmod(stream.fileno(),path.stat().st_mode&0o777)
        stream.flush();os.fsync(stream.fileno())
    temp.replace(path)
    descriptor=os.open(path.parent,os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)

qualification=dict(status='PASS',boot_id=boot,normal_reboot_verified=True,
    first_image_counter_s=proof['logo']['lit_counter_s'],
    asset_load_elapsed_s=proof['logo']['load_elapsed_s'],
    native_framebuffer_sha256=proof['retained_splash_pixel_sha256'],
    native_desktop_and_touch_matrix=proof['native_desktop_and_touch_matrix'],
    combined_load_seconds=load['seconds'],combined_load_status=load['status'],
    handoff_revision=2,physical_power_key_test_for_this_image=False,
    visual_confirmation=proof['visual_confirmation'],qualified_unix=int(time.time()))
manifest.update(hardware_boot_verified=True,hardware_qualification=qualification)
atomic(folder/'loader.toc0.json',manifest)
panel_path=state/'boot-panel-installed.json';panel=json.loads(panel_path.read_text())
historical_keys=('user_first_light_confirmation','key_on_lit_counter_s',
                 'user_right_landscape_and_touch_confirmed','normal_verified_boot_id')
if 'previous_colorbar_qualification' not in panel:
    panel['previous_colorbar_qualification']={key:panel.pop(key) for key in historical_keys if key in panel}
    panel['previous_colorbar_qualification']['scope']='Previous hardware colorbar loader, before custom image'
panel.update(custom_boot_logo=True,custom_image_qualification=qualification,
             normal_verified_boot_id=boot)
atomic(panel_path,panel)
installed['files'][str(panel_path)]['installed_sha256']=hashlib.sha256(panel_path.read_bytes()).hexdigest()
installed['qualification']=qualification
atomic(state/'boot-logo-installed.json',installed)
print('BOOT_LOGO_FINAL_QUALIFICATION_RECORDED',json.dumps(qualification),flush=True)
