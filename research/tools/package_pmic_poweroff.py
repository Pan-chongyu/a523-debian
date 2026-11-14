"""Package the power-off addition separately from the trained DRAM/GPU baseline."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
stage = root/'build/pmic-poweroff/stage'
files = {
    'usr/local/lib/tzx-pmic-poweroff/tzx_pmic_poweroff.ko': root/'build/pmic-poweroff/tzx_pmic_poweroff.ko',
    'usr/local/lib/tzx-pmic-poweroff/runtime.py': root/'firmware/tzx_pmic_poweroff_runtime.py',
    'usr/local/lib/tzx-pmic-poweroff/read_pmic_shutdown_status.py': root/'firmware/read_pmic_shutdown_status.py',
    'etc/systemd/system/tzx-pmic-poweroff.service': root/'firmware/tzx-pmic-poweroff.service',
}
contents = {name: path.read_bytes() for name, path in files.items()}
assert hashlib.sha256(contents['usr/local/lib/tzx-pmic-poweroff/tzx_pmic_poweroff.ko']).hexdigest() == 'eabf81dae1d5cf430ad4791c0dacd625825e15690ffeff919caf7c59d0ff9af8'
for name, data in contents.items():
    if name.endswith('.py'):
        compile(data, name, 'exec')
    target = stage/name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
hashes = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
contents['FILES.json'] = json.dumps(hashes, indent=2).encode()+b'\n'
destination = root/'build/pmic-poweroff/pmic-poweroff-runtime.tar.gz'
with tarfile.open(destination, 'w:gz') as archive:
    for name, data in sorted(contents.items()):
        member = tarfile.TarInfo(name)
        member.size, member.mode = len(data), 0o644
        archive.addfile(member, io.BytesIO(data))
with tarfile.open(destination, 'r:gz') as archive:
    for name, data in contents.items():
        assert archive.extractfile(name).read() == data
record = {'package_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
          'files': hashes, 'module_loaded_unloaded_and_normal_reboot_tested': True,
          'actual_poweroff_and_cold_boot_tested': False}
(root/'build/pmic-poweroff/PACKAGE.json').write_text(json.dumps(record, indent=2)+'\n')
print('PMIC_POWEROFF_PACKAGE_MEMBERS_VERIFIED', json.dumps(record))
