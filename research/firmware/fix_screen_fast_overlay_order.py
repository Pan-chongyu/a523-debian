"""Order the video SID overlay after thermal SID rebinding; preserve the failed trial."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.geteuid() == 0
state = Path('/var/lib/tzx')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot == '572b1e51-6e7f-4822-8ddf-565cada8bc68'
assert Path('/proc/sys/kernel/tainted').read_text().strip() == '4608'
sha = lambda b: hashlib.sha256(b).hexdigest()
installed = json.loads((state/'screen-fast-installed.json').read_text())
for name, item in installed['files'].items():
    assert sha(Path(name).read_bytes()) == item['installed_sha256'], name
backup = Path('/root/tzx-recovery/screen-fast-rail-v1/failed-trial-1')
backup_existed = backup.exists()
log = subprocess.check_output(['dmesg'],text=True)
assert "Don't multithread overlaying and probing the same device!" in log
assert 'fw_devlink_refresh_fwnode' in log and '[tzx_video_nodes]' in log
assert not any(v in log for v in ('BUG:', 'Oops:', 'SError'))
gpu_revoke = json.loads((state/'dram-gpu-revoked.json').read_text())
assert gpu_revoke['boot_id'] == boot and gpu_revoke['reason'] == 'GPU startup or health failure'
hs_failure = json.loads((state/'emmc-hs-failure.json').read_text())
assert hs_failure == dict(boot_id=boot, error="AssertionError('screen-boot-health.json')")
gpu_original = Path('/home/debian/recovery-gpu-qualified.json').read_bytes()
hs_original = Path('/home/debian/recovery-emmc-hs-qualified.json').read_bytes()
assert json.loads(gpu_original) == gpu_revoke['previous']
assert hs_original == (state/'emmc-hs-revoked.json').read_bytes()
assert not (state/'gpu-qualified').exists() and not (state/'emmc-hs-qualified.json').exists()
for component in ('tzx-cpu-full','tzx-gpu-devfreq','tzx-emmc-hs'):
    manifest = json.loads((Path('/usr/local/lib')/component/'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        assert sha(Path(name).read_bytes()) == digest, name
if not backup_existed:
    backup.mkdir()
    (backup/'kernel-warning.txt').write_text(log)
    (backup/'failed-units.txt').write_text(subprocess.check_output(
        ['systemctl','--failed','--plain','--no-legend'],text=True))
    for name in ('dram-gpu-revoked.json','emmc-hs-failure.json','emmc-hs-revoked.json',
                 'screen-fast-installed.json','screen-fast-reboot-request.json'):
        (backup/name).write_bytes((state/name).read_bytes())
else:
    assert json.loads((backup/'dram-gpu-revoked.json').read_text())['boot_id'] == boot
    assert json.loads((backup/'screen-fast-installed.json').read_text())['files'] == installed['files']
dropin = Path('/etc/systemd/system/tzx-video.service.d/99-sid-thermal-order.conf')
assert not dropin.exists()
data = b'[Unit]\nRequires=tzx-thermal.service\nAfter=tzx-thermal.service\n'
dropin.parent.mkdir(exist_ok=True)
dropin.write_bytes(data)
dropin.chmod(0o644)
try:
    subprocess.run(['systemd-analyze','verify','--man=no','tzx-video.service','tzx-thermal.service','tzx-display.service','lightdm.service'],check=True,timeout=30)
    subprocess.run(['systemctl','daemon-reload'],check=True,timeout=20)
    installed['files'][str(dropin)] = dict(original_sha256=None,installed_sha256=sha(data),mode=0o644)
    installed.update(state='SID-overlay-order-fixed-pending-second-reboot',
        failed_trial_boot_id=boot, failed_trial_backup=str(backup),
        overlay_fix='Video adds SID cells only after thermal has completed SID unbind/rebind; no taint guard relaxed.')
    (state/'screen-fast-installed.json').write_text(json.dumps(installed,indent=2)+'\n')
    (state/'gpu-qualified').write_bytes(gpu_original)
    (state/'gpu-qualified').chmod(0o600)
    (state/'emmc-hs-qualified.json').write_bytes(hs_original)
    (state/'emmc-hs-qualified.json').chmod(0o600)
    restored = dict(gpu_qualification_sha256=sha(gpu_original),HS200_qualification_sha256=sha(hs_original),
        reason='Unchanged previously qualified components; only boot dependency ordering changed.',
        no_taint_or_thermal_guard_relaxed=True)
    (backup/'exact-qualification-restore.json').write_text(json.dumps(restored,indent=2)+'\n')
    (state/'screen-fast-reboot-request.json').write_text(json.dumps(dict(previous_boot_id=boot,
        requested_unix=int(time.time()),normal_reboot=True,trial=2,failed_trial_preserved=True),indent=2)+'\n')
    os.sync()
except BaseException:
    dropin.unlink(missing_ok=True)
    subprocess.run(['systemctl','daemon-reload'],check=True,timeout=20)
    raise
print('SCREEN_FAST_SID_OVERLAY_ORDER_FIXED_REBOOT_REQUESTED',json.dumps(restored),flush=True)
subprocess.run(['systemd-run','--unit=tzx-screen-fast-fixed-reboot','--on-active=3s',
    '/usr/bin/systemctl','reboot'],check=True,timeout=15)
