import json,signal,subprocess,time
from pathlib import Path
path=Path('/sys/bus/platform/devices/2009800.lradc/raw')
started=time.monotonic()
def stop(signum,frame): raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
last=None
try:
    while time.monotonic()-started<180:
        values=[int(x,16) for x in path.read_text().split()]
        current=values[3:]
        if current!=last:
            print(json.dumps({'second':round(time.monotonic()-started,3),'raw_channel0':values[3]&63,'raw_channel1':values[4]&63,'status':hex(values[2])}),flush=True)
            last=current
        time.sleep(.025)
finally:
    subprocess.run(['rmmod','tzx_lradc_diagnostic'],check=True)
    print('LRADC_DIAGNOSTIC_RESTORED',flush=True)
