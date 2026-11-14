#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
test "$(id -u)" = 0 || { echo 'Run sudo ./flash.sh'; exit 1; }
test -d .venv || python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
exec .venv/bin/python flash.py "$@"
