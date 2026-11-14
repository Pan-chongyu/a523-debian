#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$task_root/build/dram-step-control"
mkdir -p "$out"
aarch64-linux-gnu-gcc -static -O2 -Wall -Wextra -Werror -fstack-protector-strong \
    -o "$out/axp717-dram-step" "$task_root/firmware/axp717_dram_step.c"
sha256sum "$out/axp717-dram-step"
