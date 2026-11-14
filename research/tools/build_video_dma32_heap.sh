#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
base=/opt/a523-debian-20261109
module="$base/tzx-video-dma32-heap"
mkdir -p "$module"
python3 - "$base" "$module" <<'PY'
import sys
from pathlib import Path
base,module=map(Path,sys.argv[1:])
text=(base/'linux-hs-source/drivers/dma-buf/heaps/system_heap.c').read_text()
text=text.replace('#include <linux/module.h>','#include <linux/module.h>\n#include <linux/of.h>')
assert text.count('flags = order_flags[i];')==1
text=text.replace('flags = order_flags[i];','flags = (order_flags[i] & ~__GFP_HIGHMEM) | GFP_DMA32;')
marker='\texp_info.name = "system";'
assert text.count(marker)==1
text=text.replace(marker,'\tif (!of_machine_is_compatible("tzx,p30a523")) return -ENODEV;\n\texp_info.name = "tzxvid";')
start=text.index('\tif (IS_ENABLED(CONFIG_HIGHMEM) ||',text.index('static int __init system_heap_create'))
end=text.index('\n\treturn 0;\n}',start)
text=text[:start]+text[end:]
text=text.replace('MODULE_DESCRIPTION("DMA-BUF System Heap");','MODULE_DESCRIPTION("TZX board DMA32 video heap, derived from Linux system heap");')
(module/'tzx_video_heap.c').write_text(text)
(module/'Makefile').write_text('obj-m := tzx_video_heap.o\n')
PY
make -C "$base/linux-hs-source" O="$base/kernel-hs-build" M="$module" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
cp "$module/tzx_video_heap.ko" "$task_root/build/video/"
cp "$module/tzx_video_heap.c" "$task_root/firmware/"
sha256sum "$task_root/build/video/tzx_video_heap.ko"
