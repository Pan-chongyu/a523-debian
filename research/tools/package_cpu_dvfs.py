import hashlib,json,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'build/cpu-dvfs'
sources={
 '/usr/local/lib/tzx-cpu-dvfs/tzx_cpufreq_dvfs.ko':out/'tzx_cpufreq_dvfs.ko',
 '/usr/local/lib/tzx-cpu-dvfs/tzx_cpu_dvfs_cooling.ko':out/'tzx_cpu_dvfs_cooling.ko',
 '/usr/local/lib/tzx-cpu-dvfs/runtime.py':root/'firmware/tzx_cpu_dvfs_runtime.py',
 '/etc/systemd/system/tzx-cpu-dvfs.service':root/'firmware/tzx-cpu-dvfs.service',
}
manifest={'profile':'DCDC1-DVFS-little1416-big1488','files':{p:hashlib.sha256(s.read_bytes()).hexdigest() for p,s in sources.items()}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(out/'runtime.tar.gz','w:gz') as archive:
 for path,source in sources.items():archive.add(source,arcname=path.lstrip('/'))
 archive.add(out/'manifest.json',arcname='usr/local/lib/tzx-cpu-dvfs/manifest.json')
print(json.dumps(manifest,indent=2))
