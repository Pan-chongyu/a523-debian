"""Explicitly inject an incomplete boot marker, verify fallback, then restore."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('operation', choices=('prepare', 'restore', 'finalize'))
a = p.parse_args()
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
ROOT = Path('/root/tzx-recovery/dram-gpu-fallback-test')
MARKER = Path('/var/lib/tzx/gpu-qualified')
PENDING = Path('/var/lib/tzx/dram-gpu-boot-pending.json')
RUNTIME = '/usr/local/lib/tzx-dram-gpu/runtime.py'


def run(*command, timeout=50):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.is_symlink()
    temporary = path.with_name(path.name+'.new')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), 0o600)
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(directory)
    os.close(directory)


def record(path, value):
    atomic(path, json.dumps(value, indent=2).encode()+b'\n')


def health():
    value = json.loads(Path('/var/lib/tzx/dram-gpu-boot-health.json').read_text())
    assert value['status'] == 'PASS' and value['boot_id'] == BOOT
    assert MARKER.exists() and not PENDING.exists()
    return value


def reboot(unit):
    os.sync()
    print(run('systemd-run', '--unit='+unit, '--on-active=3s', '/usr/bin/systemctl', 'reboot'), flush=True)


assert os.geteuid() == 0
print(run('python3', RUNTIME, 'guard'), flush=True)
if a.operation == 'prepare':
    assert not ROOT.exists()
    health()
    coexist = json.loads(Path('/var/lib/tzx/dram-gpu-cpufreq-coexistence.json').read_text())
    assert coexist['result'] == 'PASS' and coexist['boot_id'] == BOOT
    assert 'ActiveState=inactive' in run('systemctl', 'show', 'tzx-dram-gpu-cpufreq-coexistence.service', '-p', 'ActiveState')
    assert run('systemctl', 'is-active', 'tzx-cpufreq.service').strip() == 'active'
    original = MARKER.read_bytes()
    atomic(ROOT/'qualification.json', original)
    record(ROOT/'intent.json', {'state': 'controlled_incomplete_boot_marker_reboot_pending',
                               'boot_id': BOOT, 'marker_sha256': hashlib.sha256(original).hexdigest(),
                               'purpose': 'Test previous-boot pending marker rejection and software fallback; not a hardware failure'})
    record(PENDING, {'boot_id': BOOT, 'health': 'controlled_incomplete_boot_marker',
                     'fault_injection_for_recovery_test': True})
    run('systemctl', 'enable', 'tzx-cpufreq.service')
    print('CONTROLLED_GPU_INCOMPLETE_BOOT_MARKER_INJECTED', BOOT, flush=True)
    reboot('tzx-controlled-gpu-fallback-reboot')
elif a.operation == 'restore':
    intent = json.loads((ROOT/'intent.json').read_text())
    assert BOOT != intent['boot_id']
    assert not MARKER.exists() and not PENDING.exists() and not Path('/sys/module/panfrost').exists()
    run('systemctl', 'is-active', 'lightdm', 'tzx-display.service', 'tzx-cpufreq.service')
    log = run('journalctl', '-b', '-u', 'tzx-gpu.service', '-u', 'tzx-dram-gpu-fallback.service', '-o', 'cat', '--no-pager')
    assert 'Previous GPU boot health did not complete' in log
    assert 'TZX_DRAM_GPU_REVOKED_SOFTWARE_DESKTOP_RESTORED' in log
    properties = run('systemctl', 'show', 'tzx-dram-gpu-fallback.service', '-p', 'Result', '-p', 'ExecMainStatus')
    assert 'Result=success' in properties and 'ExecMainStatus=0' in properties
    graphics = run('env', 'DISPLAY=:0', 'XAUTHORITY=/run/lightdm/root/:0', 'glxinfo', '-B')
    assert 'llvmpipe' in graphics
    original = (ROOT/'qualification.json').read_bytes()
    assert hashlib.sha256(original).hexdigest() == intent['marker_sha256']
    revoked = json.loads(Path('/var/lib/tzx/dram-gpu-revoked.json').read_text())
    assert revoked['boot_id'] == BOOT and revoked['previous'] == json.loads(original)
    proof = {'state': 'controlled_previous_boot_guard_and_software_fallback_PASS',
             'boot_before_injection': intent['boot_id'], 'fallback_boot': BOOT,
             'journal_sha256': hashlib.sha256(log.encode()).hexdigest(),
             'actual_software_renderer': 'llvmpipe', 'hardware_failure': False}
    record(ROOT/'fallback-result.json', proof)
    print('CONTROLLED_GPU_PREVIOUS_BOOT_GUARD_AND_SOFTWARE_FALLBACK_PASS', json.dumps(proof), flush=True)
    run('systemctl', 'stop', 'lightdm')
    run('systemctl', 'stop', 'tzx-display.service')
    run('systemctl', 'reset-failed', 'tzx-gpu.service', 'tzx-dram-gpu-health.service')
    atomic(MARKER, original)
    run('systemctl', 'start', 'tzx-display.service')
    run('systemctl', 'start', 'tzx-gpu.service')
    run('systemctl', 'start', 'lightdm')
    run('systemctl', 'restart', 'tzx-dram-gpu-health.service', timeout=115)
    proof['accelerated_desktop_restored_health'] = health()
    proof['state'] = 'recovery_PASS_normal_autostart_reboot_pending'
    record(ROOT/'fallback-result.json', proof)
    print('CONTROLLED_GPU_RECOVERY_ACCELERATED_DESKTOP_RESTORED', json.dumps(proof), flush=True)
    reboot('tzx-gpu-cpufreq-normal-autostart-reboot')
else:
    proof = json.loads((ROOT/'fallback-result.json').read_text())
    assert BOOT != proof['fallback_boot']
    final_health = health()
    services = ('tzx-display', 'tzx-touch', 'tzx-wifi', 'tzx-bluetooth', 'tzx-audio', 'tzx-battery',
                'tzx-thermal', 'tzx-tablet-keys', 'lightdm', 'tzx-rtc-log', 'tzx-cpufreq',
                'tzx-gpu', 'tzx-dram-gpu-health')
    for service in services:
        assert run('systemctl', 'is-active', service+'.service').strip() == 'active', service
    assert run('systemctl', '--failed', '--no-legend').strip() == ''
    audit = run('systemctl', 'show', 'tzx-dram-gpu-final-files.service',
                '-p', 'Result', '-p', 'ExecMainStatus', '-p', 'ActiveState')
    assert all(v in audit for v in ('Result=success', 'ExecMainStatus=0', 'ActiveState=inactive'))
    audit_log = run('journalctl', '-b', '-u', 'tzx-dram-gpu-final-files.service', '-o', 'cat', '--no-pager')
    assert 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS' in audit_log
    policies = []
    for cpu in (0, 4):
        path = Path('/sys/devices/system/cpu/cpufreq')/f'policy{cpu}'
        value = {name: (path/name).read_text().strip() for name in
                 ('scaling_driver', 'scaling_governor', 'scaling_min_freq', 'scaling_max_freq', 'cpuinfo_cur_freq')}
        assert value['scaling_driver'] == 'tzx-a523-divider' and value['scaling_governor'] == 'schedutil'
        assert value['scaling_min_freq'] == '120000' and value['scaling_max_freq'] == '480000'
        policies.append(value)
    state = Path('/var/lib/tzx/dram-gpu-runtime-installed.json')
    installed = json.loads(state.read_text())
    proof.update(state='controlled_recovery_and_normal_autostart_verified',
                 normal_autostart_boot_id=BOOT)
    record(ROOT/'fallback-result.json', proof)
    installed.update(state='accelerated_autostart_cpufreq_and_controlled_recovery_verified',
                     verified_boot_id=BOOT, controlled_fallback_test=proof, final_boot_health=final_health,
                     cpufreq_policies=policies)
    record(state, installed)
    profile = json.loads(MARKER.read_text())
    profile.update(state='accelerated_autostart_and_divider_coexistence_verified',
                   autostart_boot_ids=['fb0eb194-3d78-4ddd-9eb4-f08b65494bc3', BOOT],
                   controlled_fallback_boot_id=proof['fallback_boot'])
    record(MARKER, profile)
    cpu_state = Path('/var/lib/tzx/cpufreq-runtime-installed.json')
    cpu = json.loads(cpu_state.read_text())
    for name, digest in cpu['files'].items():
        assert hashlib.sha256((Path('/')/name).read_bytes()).hexdigest() == digest, name
    cpu.update(coexistence_verified_boot_id=BOOT, gpu_enabled=True,
               trained_dram_setpoint_mV=1260, coexistence_profile=profile['profile'],
               coexistence_file_audit_journal_sha256=hashlib.sha256(audit_log.encode()).hexdigest())
    record(cpu_state, cpu)
    record(Path('/var/lib/tzx/dram-gpu-coexistence-final.json'),
           {'boot_id': BOOT, 'result': 'PASS', 'boot_health': final_health,
            'services_active': list(services), 'failed_units': 0, 'cpufreq': policies,
            'controlled_fallback': proof})
    print('DRAM_GPU_CPUFREQ_AUTOSTART_AND_CONTROLLED_RECOVERY_PASS', json.dumps(installed), flush=True)
