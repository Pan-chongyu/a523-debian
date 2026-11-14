"""Certify an actual normal reboot and the current boot's production load tests."""
import hashlib
import json
from pathlib import Path
import subprocess

STATE = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
previous = 'adf71c15-fdfb-449f-a30d-854879e00fa3'
assert boot != previous
load_path = STATE/'performance-installed-validation.json'
load = json.loads(load_path.read_text())
assert load['status'] == 'PASS' and load['boot_id'] == boot
assert load['actual_cpu_maximum_khz'] == [792000,1008000]
assert load['actual_gpu_maximum_hz'] == 600000000
assert len([e for e in load['events'] if isinstance(e,dict) and e['memory_mib'] == 2560]) == 3
idle = json.loads((STATE/'performance-idle-validation.json').read_text())
assert idle['boot_id'] == boot and idle['status'] == 'PASS'
screen = json.loads((STATE/'screen-boot-health.json').read_text())
dram = json.loads((STATE/'dram-gpu-boot-health.json').read_text())
assert screen['boot_id'] == dram['boot_id'] == boot
assert screen['result'] == dram['status'] == 'PASS'
assert dram['full_4GiB'] and dram['actual_setpoint_mV'] == 1260
assert screen['display_setup']['touch_properties'].count('0.000000, 1.000000, 0.000000, -1.000000, 0.000000, 1.000000, 0.000000, 0.000000, 1.000000') == 1
assert screen['display_setup']['fbcon_rotate'] == '1'
assert 'current 1280 x 800' in load['xrandr'] and ' right (' in load['xrandr']
shutdown = subprocess.check_output(['journalctl','-b','-1','-u','tzx-cpu-performance.service',
    '-u','tzx-gpu-performance.service','--since','2026-11-13 11:31:00','--no-pager'],text=True)
assert 'CPU_PERFORMANCE_ORIGINAL_DRIVER_AND_THERMAL_POLICY_RESTORED' in shutdown
assert 'GPU_PERFORMANCE_200_MHZ_RESTORED' in shutdown
assert 'Failed' not in shutdown and 'Traceback' not in shutdown
startup = subprocess.check_output(['journalctl','-b','-u','tzx-cpu-performance.service',
                                  '-u','tzx-gpu-performance.service','--no-pager'],text=True)
assert '11:33:' in startup and 'TZX_DRAM_GPU_HARDWARE_GUARD_PASS' in startup
assert 'actual clock:\t22222222 Hz' in Path('/sys/kernel/debug/mmc1/ios').read_text()
record = {'status':'PASS','previous_boot_id':previous,'boot_id':boot,
    'normal_reboot_verified':True,'poweroff_key_on_verified':False,
    'screen_right_landscape_and_touch_matrix':'PASS','full_4GiB_and_training_voltage':'PASS',
    'CPU_GPU_automatic_start_observed_before_manual_load_test':True,
    'cpu_actual_maximum_khz':load['actual_cpu_maximum_khz'], 'gpu_maximum_hz':load['actual_gpu_maximum_hz'],
    'load_record_sha256':hashlib.sha256(load_path.read_bytes()).hexdigest(),
    'load_record':load,'idle_record':idle,
    'old_boot_performance_shutdown_log':shutdown,'new_boot_performance_log':startup}
target = STATE/'performance-reboot-qualified.json'
assert not target.exists()
target.write_text(json.dumps(record,indent=2)+'\n')
for kind in ('cpu','gpu','wifi'):
    for suffix in (('installed',) if kind == 'wifi' else ('installed','qualified')):
        p = STATE/(kind+'-performance-'+suffix+'.json')
        current = json.loads(p.read_text())
        current['normal_reboot_validation'] = {'status':'PASS','boot_id':boot,
            'record':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'poweroff_key_on_verified':False}
        temporary = p.with_suffix('.json.rebootproof')
        temporary.write_text(json.dumps(current,indent=2)+'\n')
        temporary.replace(p)
print('PERFORMANCE_ACTUAL_NORMAL_REBOOT_QUALIFIED',json.dumps({
    'boot_id':boot,'previous_boot_id':previous,'normal_reboot_verified':True,
    'poweroff_key_on_verified':False,'maximum_temperature_mc':max(load['peaks_mc'].values())}))
