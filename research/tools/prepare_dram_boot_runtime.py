"""Permit exactly the new signed TOC0 in the retained RTC context logger."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root/'build/dram-boot-voltage'
manifest = json.loads((folder/'loader.toc0.json').read_text())
source = (root/'build/rtc-context/runtime.py').read_text()
old = 'ba98d2e683cbb49972af185c185826678de39488da96e2a43503eadc201071df'
assert source.count("== '"+old+"'") == 1
source = source.replace("== '"+old+"'", "in ('"+old+"', '"+manifest['image_sha256']+"')")
compile(source, 'rtc-context-boot-voltage-runtime.py', 'exec')
target = folder/'rtc-context-runtime.py'
target.write_text(source, encoding='utf8', newline='\n')
record = {'old_runtime_sha256': hashlib.sha256((root/'build/rtc-context/runtime.py').read_bytes()).hexdigest(),
          'new_runtime_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'allowed_TOC0_sha256': [old, manifest['image_sha256']]}
(folder/'RTC_RUNTIME.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record))
