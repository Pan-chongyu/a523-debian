"""Archive authored CPU clock patches for review, without applying them."""
import concurrent.futures
import hashlib
import json
import mailbox
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
out = root / 'upstream/a523-cpu-clock-v3'
out.mkdir(parents=True, exist_ok=True)

series_url = 'https://patchwork.armbian.eu/series/783/mbox/'
try:
    with urllib.request.urlopen(series_url, timeout=20) as response:
        series = response.read(1024 * 1024)
    assert series.count(b'From patchwork ') == 4
    assert b'20260925225112.14081-2-andre.przywara@arm.com' in series
    (out / 'series.mbox').write_bytes(series)
    messages = list(mailbox.mbox(str(out / 'series.mbox')))
    records = []
    assert len(messages) == 4
    for number, message in enumerate(messages, 1):
        assert message['Message-ID'] == f'<20260925225112.14081-{number+1}-andre.przywara@arm.com>'
        data = message.get_payload(decode=True)
        assert b'diff --git ' in data and b'Signed-off-by: Andre Przywara' in data
        name = f'{number:02d}.patch'
        (out / name).write_bytes(data)
        records.append({'file': name, 'message_id': message['Message-ID'],
                        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'applied': False})
    prior = out / 'SOURCES.json'
    if prior.exists() and not (out / 'SOURCES-before-patchwork.json').exists():
        (out / 'SOURCES-before-patchwork.json').write_bytes(prior.read_bytes())
    prior.write_text(json.dumps({'series': 'Andre Przywara A523 CPU clocks v3',
        'url': series_url, 'mbox_sha256': hashlib.sha256(series).hexdigest(),
        'status': 'download_only_not_applied_or_hardware_tested', 'records': records}, indent=2) + '\n')
    print('AUTHORED_CPU_CLOCK_V3_SERIES_ARCHIVED_NOT_APPLIED', len(records))
    raise SystemExit(0)
except (OSError, AssertionError) as error:
    print('PATCHWORK_SERIES_UNAVAILABLE', str(error))


def fetch(number):
    message = f'20260925225112.14081-{number + 1}-andre.przywara@arm.com'
    errors = []
    for archive in ('https://lore.kernel.org/linux-clk/',
                    'https://lore-kernel.gnuweeb.org/linux-devicetree/'):
        url = archive + message + '/raw'
        try:
            with urllib.request.urlopen(url, timeout=18) as response:
                data = response.read(2 * 1024 * 1024)
            assert b'diff --git ' in data and b'Signed-off-by: Andre Przywara' in data
            assert b'<html' not in data[:1000].lower()
            name = f'{number:02d}.patch'
            (out / name).write_bytes(data)
            return {'file': name, 'url': url, 'sha256': hashlib.sha256(data).hexdigest(),
                    'bytes': len(data), 'applied': False}
        except Exception as error:
            errors.append({'url': url, 'error': str(error)})
    return {'patch': number, 'errors': errors, 'applied': False}


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(fetch, range(1, 5)))
(out / 'SOURCES.json').write_text(json.dumps({'series': 'Andre Przywara A523 CPU clocks v3',
     'status': 'download_only_not_applied_or_hardware_tested', 'records': records}, indent=2) + '\n')
print(json.dumps(records, indent=2))
