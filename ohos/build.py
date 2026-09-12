#!/usr/bin/env python3
"""Build the JavaScript distribution and bundle fixed WASM runtime inputs offline."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
package = output / 'package'
package.mkdir()
source = output / 'source'
source.mkdir()
def copy_tree(origin, target):
    for path in origin.rglob('*'):
        if path.is_file():
            destination = target / path.relative_to(origin)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)

for folder in ['lib', 'scripts']:
    copy_tree(root / folder, source / folder)
shutil.copyfile(root / 'package.json', source / 'package.json')
subprocess.run(['node', str(source / 'scripts/build.mjs')], check=True)
copy_tree(source / 'dist', package / 'dist')
inputs = json.loads((root / 'ohos/SOURCES.json').read_text())
versions = {}
for entry in inputs['dependencies']:
    archive = root / entry['archive']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError(f"input checksum mismatch: {archive}")
    destination = package / 'node_modules' / entry['name']
    destination.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        for item in tar:
            path = Path(item.name)
            if not path.parts or path.parts[0] != 'package' or '..' in path.parts:
                raise ValueError(f'unsafe dependency entry: {item.name}')
            if item.isdir(): continue
            if not item.isfile(): raise ValueError(f'unsupported dependency entry: {item.name}')
            target = destination.joinpath(*path.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(item) as stream, target.open('wb') as out:
                shutil.copyfileobj(stream, out)
    manifest = json.loads((destination / 'package.json').read_text())
    assert manifest['name'] == entry['name'] and manifest['version'] == entry['version']
    versions[entry['name']] = entry['version']
manifest = json.loads((root / 'package.json').read_text())
for field in ['scripts', 'devDependencies', 'optionalDependencies', 'files', 'peerDependenciesMeta']:
    manifest.pop(field, None)
manifest.update(dependencies=versions, bundledDependencies=list(versions), os=['openharmony'], cpu=['arm64'])
(package / 'package.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
for filename in ['LICENSE', 'README.md']:
    shutil.copyfile(root / filename, package / filename)
shutil.copyfile(root / 'ohos/README.md', package / 'README.ohos.md')
shutil.copyfile(root / 'ohos/SOURCES.json', package / 'SOURCES.json')
(package / 'build-info.json').write_text(json.dumps({
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
    'node': subprocess.check_output(['node', '--version'], text=True).strip(),
    'runtime': 'upstream @img/sharp-wasm32 0.35.3, bundled without modification',
}, indent=2) + '\n')
archive = output / f"sharp-{manifest['version']}.tgz"
with archive.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', mtime=0, filename='') as zipped:
    with tarfile.open(fileobj=zipped, mode='w|') as tar:
        for path in sorted(package.rglob('*')):
            if not path.is_file(): continue
            info = tar.gettarinfo(str(path), 'package/' + str(path.relative_to(package)))
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ''
            info.mode = 0o644
            with path.open('rb') as source: tar.addfile(info, source)
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_name(archive.name + '.sha256').write_text(f'{sha}  {archive.name}\n')
print(f'BUILT {archive.name} {archive.stat().st_size} {sha}; native acceptance is required separately')
