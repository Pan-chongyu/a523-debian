"""Verify the real launch request, expiry, watchdog cleanup and user fallback."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

assert os.geteuid()==0
policies=[Path('/sys/devices/system/cpu/cpufreq')/('policy'+str(n)) for n in (0,4)]
read=lambda:[int((p/'scaling_min_freq').read_text()) for p in policies]
def main_pid():return int(subprocess.check_output(['systemctl','show','tzx-app-boost','-p','MainPID','--value'],text=True))
def launch():
    started=time.monotonic()
    result=subprocess.check_output(['/usr/local/bin/tzx-launch','/usr/bin/id','-u'],user=1000,group=1000,extra_groups=os.getgrouplist('debian',1000),text=True,timeout=2)
    assert result.strip()=='1000'
    return round((time.monotonic()-started)*1000,3)
subprocess.run(['python3','/home/debian/install_app_launch.py','verify'],check=True)
assert read()==[120000,120000],read()
cpu_pid=subprocess.check_output(['systemctl','show','tzx-cpu-dvfs','-p','MainPID','--value'],text=True).strip()
maximum=[int((p/'scaling_max_freq').read_text()) for p in policies]
assert maximum==[1416000,1800000]
latency=launch();assert read()==maximum,read()
started=time.monotonic()
while time.monotonic()-started<7:
    if read()==[120000,120000]:break
    time.sleep(.05)
else:raise RuntimeError('launch boost did not expire')
expiry=round(time.monotonic()-started,3)
assert 3.5<expiry<5.0,expiry
old=main_pid();launch();assert read()==maximum
started=time.monotonic();os.kill(old,signal.SIGSTOP)
try:
    while time.monotonic()-started<15:
        new=main_pid()
        if new and new!=old and read()==[120000,120000]:break
        time.sleep(.15)
    else:raise RuntimeError('systemd watchdog did not restore the floor and restart')
finally:
    if main_pid()==old:
        os.kill(old,signal.SIGCONT)
        subprocess.run(['systemctl','stop','tzx-app-boost'],check=True,timeout=10)
        subprocess.run(['systemctl','start','tzx-app-boost'],check=True,timeout=10)
watchdog=round(time.monotonic()-started,3)
assert subprocess.check_output(['systemctl','show','tzx-cpu-dvfs','-p','MainPID','--value'],text=True).strip()==cpu_pid
subprocess.run(['systemctl','stop','tzx-app-boost'],check=True,timeout=10)
fallback_latency=launch();assert read()==[120000,120000]
subprocess.run(['systemctl','start','tzx-app-boost'],check=True,timeout=10)
assert read()==[120000,120000]
preferred=subprocess.check_output(['runuser','-u','debian','--','env','DISPLAY=:0','XAUTHORITY=/home/debian/.Xauthority',
    'xfce4-mime-helper','--query','WebBrowser'],text=True).strip()
assert preferred=='tzx-firefox',preferred
assert not subprocess.check_output(['systemctl','--failed','--plain','--no-legend'],text=True).strip()
record=dict(status='PASS',boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    request_and_exec_milliseconds=latency,expiry_seconds=expiry,watchdog_and_restart_seconds=watchdog,
    daemon_unavailable_exec_milliseconds=fallback_latency,exec_uid=1000,
    cpu_owner_pid_unchanged=cpu_pid,minimum_after_test_khz=read(),preferred_browser=preferred,
    maximum_khz=maximum,thermal_maximum_untouched=True)
Path('/var/lib/tzx/app-launch-controls-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
print('APP_LAUNCH_REAL_EXPIRY_WATCHDOG_AND_UNPRIVILEGED_EXEC_PASS',json.dumps(record),flush=True)
