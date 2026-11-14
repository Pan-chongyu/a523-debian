"""Freeze cooling plus the minimal GPU physical/aggregate zone inventory change."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
sources = {
    'usr/local/lib/tzx-cpu-cooling/tzx_cpu_cooling.ko': root/'build/cpu-cooling/tzx_cpu_cooling.ko',
    'usr/local/lib/tzx-cpu-cooling/runtime.py': root/'firmware/tzx_cpu_cooling_runtime.py',
    'etc/systemd/system/tzx-cpu-cooling.service': root/'firmware/tzx-cpu-cooling.service',
    'usr/local/lib/tzx-dram-gpu/runtime.py': root/'build/cpu-cooling/gpu-runtime-cooling.py',
}
contents = {name: path.read_bytes() for name, path in sources.items()}
hashes = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
assert hashes['usr/local/lib/tzx-cpu-cooling/tzx_cpu_cooling.ko'] == 'd37b67d234a699a45eaf0c7f9c350123271754091a77c498a6f99e883ac37efa'
assert hashes['usr/local/lib/tzx-dram-gpu/runtime.py'] == 'f708504a8e430ef8259b3af6a0b2c0fbb8bf64ff7c534e51d8754aa322f12690'
for name, data in contents.items():
    if name.endswith('.py'):
        compile(data, name, 'exec')
    path = root/'build/cpu-cooling/stage'/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
contents['FILES.json'] = json.dumps(hashes, indent=2).encode()+b'\n'
target = root/'build/cpu-cooling/cpu-cooling-runtime.tar.gz'
with tarfile.open(target, 'w:gz') as archive:
    for name, data in sorted(contents.items()):
        member = tarfile.TarInfo(name)
        member.mode, member.size = 0o644, len(data)
        archive.addfile(member, io.BytesIO(data))
with tarfile.open(target, 'r:gz') as archive:
    for name, data in contents.items():
        assert archive.extractfile(name).read() == data
record = {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'files': hashes,
          'qualification': 'requires real-temperature lowered-trip tests and actual autostart reboot',
          'boot_PMIC_PLL_changes': False}
(target.parent/'PACKAGE.json').write_text(json.dumps(record, indent=2)+'\n')
print('CPU_COOLING_PACKAGE_MEMBERS_VERIFIED', json.dumps(record))
