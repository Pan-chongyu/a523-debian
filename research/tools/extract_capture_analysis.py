"""Extract the single capture JSON object from a combined command log."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('source',type=Path)
parser.add_argument('target',type=Path)
args = parser.parse_args()
raw = args.source.read_text(encoding='utf8')
for position,char in enumerate(raw):
    if char != '{':
        continue
    try:
        item,_ = json.JSONDecoder().raw_decode(raw[position:])
    except json.JSONDecodeError:
        continue
    if isinstance(item,dict) and 'prefix' in item and 'captures' in item:
        assert not args.target.exists()
        args.target.write_text(json.dumps(item,indent=2)+'\n',encoding='utf8')
        print('CAPTURE_ANALYSIS_EXTRACTED',args.target)
        break
else:
    raise AssertionError('No capture analysis found')
