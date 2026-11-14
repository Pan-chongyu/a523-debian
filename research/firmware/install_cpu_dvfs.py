"""Install the independently qualified voltage-aware CPU stack."""
import hashlib,json,os,subprocess,sys,tarfile,time
from pathlib import Path
assert os.geteuid()==0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert sys.argv[1] in ('install','restore')
root=Path('/usr/local/lib/tzx-cpu-dvfs')
unit='tzx-cpu-dvfs.service'
qualified=Path('/var/lib/tzx/cpu-dvfs-qualified.json')
state_path=Path('/var/lib/tzx/cpu-dvfs-installed.json')
def run(*command):return subprocess.check_output(command,text=True,stderr=subprocess.STDOUT,timeout=90)
if sys.argv[1]=='restore':
 run('systemctl','disable','--now',unit)
 run('systemctl','start','tzx-cpufreq.service','tzx-cpu-cooling.service')
 run('systemctl','enable','--now','tzx-cpu-performance.service')
 qualified.unlink(missing_ok=True)
 print('CPU_DVFS_DISABLED_PRIOR_792_1008_MHZ_STACK_RESTORED')
 raise SystemExit(0)
assert not root.exists() and not state_path.exists()
trial=json.loads(Path('/home/debian/cpu-dvfs/trial-result.json').read_text())
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert trial['status']=='PASS' and trial['baseline_restored'] and trial['boot_id']==boot
assert trial['clock_transitions']==160 and trial['eight_core_checksums']==40
assert trial['thermal_qos_240MHz']=='PASS' and trial['lease_expiry_480MHz_900mV']=='PASS'
for cpu,frequency in ((0,1416000),(4,1488000)):
 baseline=next(r for r in trial['records'] if r['stage']=='baseline' and r['cpu']==cpu)
 high=next(r for r in trial['records'] if r['stage']=='new-driver' and r['cpu']==cpu and r['khz']==frequency)
 assert baseline['median_thread_seconds']/high['median_thread_seconds']>2.7
previous_enabled=run('systemctl','is-enabled','tzx-cpu-performance.service').strip()
with tarfile.open('/home/debian/cpu-dvfs-runtime.tar.gz') as archive:
 members=archive.getmembers()
 expected={'usr/local/lib/tzx-cpu-dvfs/'+n for n in ('tzx_cpufreq_dvfs.ko','tzx_cpu_dvfs_cooling.ko','runtime.py','manifest.json')}|{'etc/systemd/system/tzx-cpu-dvfs.service'}
 assert {m.name for m in members}==expected
 for member in members:
  assert member.isfile() and '..' not in Path(member.name).parts
  target=Path('/')/member.name
  assert not target.exists() and not target.is_symlink()
  target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(archive.extractfile(member).read())
  target.chmod(0o644)
manifest=json.loads((root/'manifest.json').read_text())
for path,digest in manifest['files'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
qualified.write_text(json.dumps({'profile':manifest['profile'],'trial':trial,'scope':'online qualified; boot verification pending'},indent=2)+'\n')
state_path.write_text(json.dumps({'manifest':manifest,'boot_id':boot,'previous_CPU_performance_enabled':previous_enabled,'state':'online-qualified','boot_areas_changed':False},indent=2)+'\n')
run('systemctl','daemon-reload')
run('systemctl','disable','--now','tzx-cpu-performance.service')
run('systemctl','start','tzx-cpufreq.service','tzx-cpu-cooling.service')
run('systemctl','enable','--now',unit)
for attempt in range(100):
 status=Path('/run/tzx-cpu-dvfs.json')
 if status.exists() and json.loads(status.read_text()).get('state')=='active':break
 assert subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0
 time.sleep(.5)
else:raise AssertionError('DVFS service did not become ready')
print('CPU_DVFS_1416_1488_MHZ_INSTALLED_WITH_THERMAL_AND_LEASE',status.read_text())
