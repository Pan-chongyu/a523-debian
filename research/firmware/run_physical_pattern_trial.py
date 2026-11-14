"""One bounded 3GiB check of private pinned RAM; no hardware register writes."""
import hashlib,json,os,subprocess
from pathlib import Path
assert os.geteuid()==0 and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip()=='3e01ff55454d20202010209170281b59'
assert Path('/sys/devices/system/cpu/online').read_text().strip()=='0-7'
assert int(Path('/proc/sys/kernel/tainted').read_text())==4096
assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256']=='3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
for name in ('panfrost','tzx_cpufreq_divider'):
    assert not Path('/sys/module',name).exists(),name
binary=Path('/home/debian/physical-memory-pattern-v2')
assert hashlib.sha256(binary.read_bytes()).hexdigest()=='588e264e1c892b800f8e8bdee7ed90efaefd615706b62bda8745ef813cb436dc'
binary.chmod(0o755)
os.sync()
Path('/proc/sys/vm/drop_caches').write_text('1\n')
print('PHYSICAL_PATTERN_BOOT',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),flush=True)
result=subprocess.run([str(binary)],timeout=240)
print('PHYSICAL_PATTERN_PROCESS_RESULT',result.returncode,flush=True)
raise SystemExit(result.returncode)
