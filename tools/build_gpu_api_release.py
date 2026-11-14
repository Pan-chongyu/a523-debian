#!/usr/bin/env python3
"""Build the GPU add-on and corresponding-source archives from verified inputs. MIT."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'gpu-api-v0.3.0'
PAYLOAD = 'a523-gpu-api-v0.3.0'
NEW_SOURCE_ASSET = 'a523-gpu-api-new-debian-sources-v0.3.0.tar.gz'
IMAGE_RELEASE = 'https://github.com/Pan-chongyu/a523-debian/releases/download/v0.1.0-20261114/'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def archive(destination, entries):
    with destination.open('wb') as target, gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w|', format=tarfile.PAX_FORMAT) as tar:
            for name, source in sorted(entries):
                if source.is_symlink() or not source.is_file() or '..' in Path(name).parts or name.startswith('/'):
                    raise ValueError('Unsafe archive input: ' + name)
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = source.stat().st_size, 0o644, 0
                info.uid = info.gid = 0
                info.uname = info.gname = 'root'
                with source.open('rb') as stream:
                    tar.addfile(info, stream)


def source_map(source_folder):
    wanted = set()
    for line in (ROOT / 'board/gpu-api-packages.tsv').read_text().splitlines():
        _, _, name, version = line.split('\t')
        wanted.add((name, version))
    old = json.loads((ROOT / 'board/debian-sources.json').read_text())
    new = json.loads((source_folder / 'source-plan.json').read_text())
    available, entries = {}, []
    for batch in old['batches']:
        for item in batch['files']:
            key = item['package'], item['version']
            if key in wanted:
                available.setdefault(key, []).append(dict(item, asset=batch['asset'],
                    asset_url=IMAGE_RELEASE + batch['asset']))
    for item in new:
        key = item['package'], item['version']
        files = []
        for f in item['files']:
            relative = Path('packages') / key[0] / key[1].replace(':', '_') / f['name']
            path = source_folder / relative
            if not path.is_file() or path.stat().st_size != f['bytes'] or digest(path) != f['sha256']:
                raise RuntimeError('Corresponding source is missing or corrupt: ' + str(relative))
            files.append(dict(f, relative=relative.as_posix(), asset=NEW_SOURCE_ASSET,
                asset_url='https://github.com/Pan-chongyu/a523-debian/releases/download/' + TAG + '/' + NEW_SOURCE_ASSET))
            entries.append((relative.as_posix(), path))
        available[key] = files
    if wanted - available.keys():
        raise RuntimeError('Source map is incomplete: ' + str(wanted - available.keys()))
    mapping = {'complete': True, 'source_packages': len(wanted), 'new_source_packages': len(new),
               'packages': [{'package': name, 'version': version, 'files': available[(name, version)]}
                            for name, version in sorted(wanted)]}
    path = ROOT / 'board/gpu-api-debian-sources.json'
    path.write_text(json.dumps(mapping, indent=2) + '\n', newline='\n')
    return mapping, entries


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary-dir', type=Path, required=True)
    p.add_argument('--source-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('gpu_packages', ROOT / 'gpu/fetch_packages.py')
    packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)
    manifest = json.loads((ROOT / 'gpu/packages.json').read_text())
    binaries = packages.verify(args.binary_dir, manifest)
    mapping, sources = source_map(args.source_dir)
    contents = []
    for path in (ROOT / 'gpu').iterdir():
        if path.is_file() and path.suffix in ('.py', '.json', '.service'):
            contents.append((PAYLOAD + '/gpu/' + path.name, path))
    contents += [(PAYLOAD + '/debs/' + path.name, path) for path in binaries]
    for relative in ('LICENSE', 'LICENSES/MIT.txt', 'LICENSES/SyterKit-GPL-2.0.txt',
                     'docs/GPU-API.md', 'docs/zh-CN/GPU-API.md', 'docs/ja/GPU-API.md', 'docs/es/GPU-API.md',
                     'board/gpu-api-packages.tsv', 'board/gpu-api-debian-sources.json'):
        contents.append((PAYLOAD + '/' + relative, ROOT / relative))
    archive(args.output / (PAYLOAD + '.tar.gz'), contents)
    sources += [('gpu-api-debian-sources.json', ROOT / 'board/gpu-api-debian-sources.json')]
    archive(args.output / NEW_SOURCE_ASSET, sources)
    for name in (PAYLOAD + '.tar.gz', NEW_SOURCE_ASSET):
        path = args.output / name
        print('GPU_ASSET_BUILT', name, path.stat().st_size, digest(path), flush=True)
    print('CORRESPONDING_SOURCES', mapping['source_packages'], 'new', mapping['new_source_packages'])


if __name__ == '__main__':
    main()
