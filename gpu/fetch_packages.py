#!/usr/bin/env python3
"""Download the exact Debian add-on packages with recorded SHA256 checks. MIT."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validated_entries(manifest):
    entries, names = manifest['files'], set()
    for entry in entries:
        name = entry['file']
        if (not name.endswith('.deb') or Path(name).name != name or '/' in name or '\\' in name
                or name in names or not 0 < entry['bytes'] < 100_000_000
                or len(entry['sha256']) != 64 or any(c not in '0123456789abcdef' for c in entry['sha256'])
                or not entry['url'].startswith('https://deb.debian.org/debian/pool/')
                or entry['architecture'] not in ('arm64', 'all')):
            raise ValueError('Invalid package entry: ' + name)
        names.add(name)
    if not entries:
        raise ValueError('Empty package manifest')
    return entries


def verify(folder, manifest):
    paths = []
    for entry in validated_entries(manifest):
        path = folder / entry['file']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise RuntimeError('Package size/SHA256 mismatch: ' + entry['file'])
        paths.append(path.resolve())
    return paths


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--manifest', type=Path, default=Path(__file__).with_name('packages.json'))
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text())
    entries = validated_entries(manifest)
    args.output.mkdir(parents=True, exist_ok=True)

    def fetch(entry):
        path = args.output / entry['file']
        if path.exists() and path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256']:
            return path
        temporary = path.with_suffix('.deb.part')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(entry['url'], timeout=40) as source, temporary.open('wb') as destination:
                    count = 0
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        count += len(block)
                        if count > entry['bytes']:
                            raise RuntimeError('Package exceeds manifest size')
                        destination.write(block)
                if temporary.stat().st_size != entry['bytes'] or digest(temporary) != entry['sha256']:
                    raise RuntimeError('Debian package digest mismatch')
                temporary.replace(path)
                print('VERIFIED', path.name, flush=True)
                return path
            except Exception:
                temporary.unlink(missing_ok=True)
                if attempt == 2:
                    raise

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(fetch, entries))
    paths = verify(args.output, manifest)
    print('ALL_PACKAGES_VERIFIED', len(paths), sum(x.stat().st_size for x in paths), flush=True)


if __name__ == '__main__':
    main()
