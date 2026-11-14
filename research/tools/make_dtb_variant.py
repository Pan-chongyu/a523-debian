"""Remove named top-level blocks from the board DTS for boot isolation tests."""
from pathlib import Path
import sys
import re

src = Path(sys.argv[1]).read_text(encoding="utf8")
names = sys.argv[2:]

def remove_block(text, marker):
    if marker.startswith('&'):
        start = re.search(r'^' + re.escape(marker) + r'\s*\{', text, re.M).start()
    else:
        start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    quote = False
    escaped = False
    for i in range(brace, len(text)):
        c = text[i]
        if quote:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quote = False
            continue
        if c == '"':
            quote = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = text.index(";", i) + 1
                return text[:start] + text[end:]
    raise ValueError(marker)

for name in names:
    src = remove_block(src, name)
src = src.replace("        i2c1 = &touch_i2c;\n", "")
base = Path(sys.argv[1])
out = base.with_name(base.stem + "-variant.dts")
out.write_text(src, encoding="utf8", newline="\n")
print(out)
