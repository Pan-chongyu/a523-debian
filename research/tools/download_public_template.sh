#!/bin/sh
set -eu
task=/opt/a523-public-release
cat > "$task/private/sftp-batch" <<'EOF'
reget /var/tmp/tzx-public-export/system-template.tar.gz /opt/a523-public-release/downloads/system-template.tar.gz
get /var/tmp/tzx-public-export/export.json /opt/a523-public-release/downloads/export.json
get /var/tmp/tzx-public-export/toc0.bin /opt/a523-public-release/downloads/toc0.bin
get /var/tmp/tzx-public-export/logo.bin /opt/a523-public-release/downloads/logo.bin
get /var/tmp/tzx-public-export/header.bin /opt/a523-public-release/downloads/header.bin
get /var/tmp/tzx-public-export/active-bundle.bin /opt/a523-public-release/downloads/active-bundle.bin
get /var/tmp/tzx-public-export/fallback-bundle.bin /opt/a523-public-release/downloads/fallback-bundle.bin
EOF
for attempt in 1 2 3 4; do
    if sftp -l 16000 -i "$task/private/key" -o UserKnownHostsFile="$task/private/known_hosts" \
        -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=10 \
        -b "$task/private/sftp-batch" debian@192.168.77.2; then break; fi
    echo "Template transfer interrupted; resuming attempt $attempt" >&2
done
python3 - <<'PY'
import hashlib,json
from pathlib import Path
p=Path('/opt/a523-public-release/downloads');m=json.loads((p/'export.json').read_text())
h=hashlib.sha256()
with (p/'system-template.tar.gz').open('rb') as f:
    for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
assert h.hexdigest()==m['archive_sha256']
for name,item in m['raw'].items():assert hashlib.sha256((p/name).read_bytes()).hexdigest()==item['sha256']
print('ALL_PUBLIC_TEMPLATE_DOWNLOADS_VERIFIED',flush=True)
PY
