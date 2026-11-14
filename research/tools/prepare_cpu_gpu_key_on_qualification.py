"""Derive the same installed-profile audit while preserving warm-boot provenance."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'firmware/qualify_cpu_gpu_reboot.py').read_text()
def replace(before,after):
    global source
    assert source.count(before)==1,before
    source=source.replace(before,after)
replace('Audit actual autostart, concurrent load, rendering and idle power after reboot.',
        'Audit the same CPU/GPU profile after PMIC off and physical key-on.')
replace("request=json.loads((state/'cpu-gpu-normal-reboot-request.json').read_text())",
        "request=json.loads((state/'cpu-gpu-key-on-request.json').read_text())\nwarm=json.loads((state/'cpu-gpu-normal-reboot-qualified.json').read_text())\nassert warm['status']=='PASS' and warm['normal_reboot_verified']")
replace("assert '#5 ' in os.uname().version", """assert '#5 ' in os.uname().version
pmic=json.loads(run('python3','/usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py'))
assert pmic['boot_id']==boot and pmic['axp323_id']=='0x49'
assert int(pmic['axp717']['0x21'],16)&2, 'No PMIC software shutdown reason'
assert int(pmic['axp717']['0x21'],16)&0xf8==0, 'Undervoltage/current/thermal shutdown reason'
assert int(pmic['axp717']['0x20'],16)&1, 'No PMIC physical key-on reason'
assert int(pmic['axp717']['0x27'],16)==8 and pmic['axp717']['0x85']=='0xc9'
print('PMIC_SOFTWARE_OFF_AND_PHYSICAL_KEY_ON_CAUSES_PASS',json.dumps(pmic),flush=True)""")
replace('normal_reboot_verified=True,poweroff_key_on_verified=False,installed_manifests=manifests,',
        "normal_reboot_verified=True,normal_reboot_id=warm['boot_id'],poweroff_key_on_verified=True,\n    pmic_status=pmic,visual_confirmation='pending',complete_battery_USB_removal_tested=False,installed_manifests=manifests,")
replace("'No physical poweroff/key-on test of this new CPU/GPU combination',",
        "'PMIC soft-off/key-on verified with battery and USB attached; not full removal of power',")
replace("target=state/'cpu-gpu-normal-reboot-qualified.json'", "target=state/'cpu-gpu-key-on-qualified.json'")
replace("value.update(normal_reboot_verified=True,normal_reboot_id=boot,\n        poweroff_key_on_verified=False,normal_reboot_proof_sha256=sha(target.read_bytes()))",
        "value.update(poweroff_key_on_verified=True,poweroff_key_on_boot_id=boot,\n        poweroff_key_on_proof_sha256=sha(target.read_bytes()))")
replace("value['state']='actual-normal-reboot-and-concurrent-load-verified'", "value['state']='actual-normal-and-physical-key-on-load-verified'")
replace("value['scope']='Qualified online, actual normal autostart and concurrent load'", "value['scope']='Qualified online, normal reboot and PMIC soft-off/physical key-on with concurrent load'")
replace('CPU_GPU_NORMAL_REBOOT_FULL_STACK_QUALIFIED','CPU_GPU_PHYSICAL_KEY_ON_FULL_STACK_QUALIFIED')
target=root/'firmware/qualify_cpu_gpu_key_on.py'
compile(source,str(target),'exec')
target.write_text(source,encoding='utf-8',newline='\n')
print('PHYSICAL_KEY_ON_QUALIFICATION_PREPARED')
