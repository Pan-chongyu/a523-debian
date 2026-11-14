#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$task_root/build/app-launch/stage"
aarch64-linux-gnu-gcc -O2 -Wall -Wextra -Werror -Wl,-z,relro,-z,now \
    "$task_root/firmware/tzx_launch.c" -o "$task_root/build/app-launch/stage/tzx-launch"
cp "$task_root/firmware/tzx_app_boost.py" "$task_root/build/app-launch/stage/boost.py"
cp "$task_root/firmware/tzx_app_cache.py" "$task_root/build/app-launch/stage/cache.py"
cp "$task_root/firmware/tzx-app-boost.service" "$task_root/build/app-launch/stage/"
cp "$task_root/firmware/tzx-app-cache.service" "$task_root/build/app-launch/stage/"
python3 - "$task_root/build/app-launch/stage" <<'PY'
import hashlib,json,sys
from pathlib import Path
folder=Path(sys.argv[1])
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.name!='manifest.json'}
(folder/'manifest.json').write_text(json.dumps({'profile':'bounded-app-boost-v1','files':files},indent=2)+'\n')
print(json.dumps(files,indent=2))
PY
