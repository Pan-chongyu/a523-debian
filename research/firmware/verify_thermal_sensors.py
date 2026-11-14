"""Log temperature response to a bounded CPU load, retaining no user data."""
import hashlib
import json
import multiprocessing
from pathlib import Path
import time


def load(deadline):
    value = bytes(65536)
    while time.monotonic() < deadline:
        value = hashlib.sha256(value).digest() * 2048


if __name__ == '__main__':
    zones = sorted(Path('/sys/class/thermal').glob('thermal_zone*'))
    assert len(zones) == 5
    children = []
    try:
        for second in range(45):
            if second == 10:
                deadline = time.monotonic() + 20
                children = [multiprocessing.Process(target=load, args=(deadline,)) for _ in range(8)]
                for child in children:
                    child.start()
            readings = {p.joinpath('type').read_text().strip(): int(p.joinpath('temp').read_text()) for p in zones}
            assert all(5000 < value < 75000 for value in readings.values()), readings
            print(json.dumps({'second': second, 'phase': 'load' if 10 <= second < 30 else 'idle',
                              'millidegrees_c': readings}), flush=True)
            time.sleep(1)
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
            child.join(timeout=2)
    assert int(Path('/proc/sys/kernel/tainted').read_text()) & 128 == 0
    print('THERMAL_RESPONSE_CHECK_FINISHED', flush=True)
