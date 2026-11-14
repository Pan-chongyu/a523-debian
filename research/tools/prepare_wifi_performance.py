"""Add bounded SDIO rates to the already qualified four-bit host source."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
out = root/'build/wifi-performance'
out.mkdir(exist_ok=True)
base = root/'build/wifi-bus-trial/tzx_wifi_runtime.c'
source = base.read_text()
needle = 'module_param(bus_width, uint, 0444);'
assert source.count(needle) == 1
source = source.replace(needle, needle+'\nstatic unsigned int max_frequency_mhz = 12;\nmodule_param(max_frequency_mhz, uint, 0444);')
needle = '    if (bus_width != 1 && bus_width != 4) {'
assert source.count(needle) == 1
source = source.replace(needle, '''    if ((max_frequency_mhz != 12 && max_frequency_mhz != 24 && max_frequency_mhz != 48) ||
        (max_frequency_mhz > 12 && bus_width != 4)) {
        ret = -EINVAL;
        goto put_node;
    }
''' + needle)
assert source.count('mmc->f_max = 12000000;') == 1
source = source.replace('mmc->f_max = 12000000;', 'mmc->f_max = max_frequency_mhz * 1000000U;')
needle = 'requested width=%u, max 12MHz\\n", bus_width);'
assert source.count(needle) == 1
source = source.replace(needle, 'requested width=%u, max %uMHz\\n", bus_width, max_frequency_mhz);')
(out/'tzx_wifi_runtime.c').write_text(source, newline='\n')
(out/'SOURCE.json').write_text(json.dumps({'base': str(base.relative_to(root)),
    'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
    'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
    'scope': 'same 3.3V SD high-speed mode; max 12/24/48 MHz; no UHS or eMMC change'}, indent=2)+'\n')
print('WIFI_SDIO_RATE_CANDIDATE_PREPARED')
