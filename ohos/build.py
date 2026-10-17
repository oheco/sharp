#!/usr/bin/env python3
"""Build sharp from this branch and bundle the fixed official WASM engine offline."""
import argparse
import base64
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
if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip():
    raise ValueError('commit the source tree before building a release')
inputs = json.loads((root / 'ohos/SOURCES.json').read_text())
manifest = json.loads((root / 'package.json').read_text())
engine = inputs['dependencies'][0]
if engine['version'] != inputs['upstream']['version'] or manifest['version'] != engine['version'] + '-ohos.1':
    raise ValueError('upstream, package and WASM engine versions must match')
for group in ['dependencies', 'provenance', 'license_files', 'test_dependencies']:
    for entry in inputs.get(group, []):
        archive = root / entry['archive']
        data = archive.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'input checksum mismatch: {archive}')
        if 'integrity' in entry:
            integrity = 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()
            if integrity != entry['integrity']:
                raise ValueError(f'input npm integrity mismatch: {archive}')

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
versions = {}
for entry in inputs['dependencies']:
    destination = package / 'node_modules' / entry['name']
    destination.mkdir(parents=True)
    with tarfile.open(root / entry['archive']) as tar:
        for item in tar:
            path = Path(item.name)
            if not path.parts or path.parts[0] != 'package' or '..' in path.parts:
                raise ValueError(f'unsafe dependency entry: {item.name}')
            if item.isdir():
                continue
            if not item.isfile():
                raise ValueError(f'unsupported dependency entry: {item.name}')
            target = destination.joinpath(*path.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(item) as stream, target.open('wb') as out:
                shutil.copyfileobj(stream, out)
    dependency = json.loads((destination / 'package.json').read_text())
    if dependency['name'] != entry['name'] or dependency['version'] != entry['version']:
        raise ValueError(f'dependency identity mismatch: {entry["name"]}')
    if not any('license' in p.name.lower() or 'copyright' in p.name.lower() for p in destination.iterdir()):
        raise ValueError(f'missing dependency license: {entry["name"]}')
    versions[entry['name']] = entry['version']
for entry in inputs['dependencies']:
    dependency = json.loads((package / 'node_modules' / entry['name'] / 'package.json').read_text())
    for name in dependency.get('dependencies', {}):
        if name not in versions:
            raise ValueError(f'unbundled transitive dependency: {name}')
for field in ['scripts', 'devDependencies', 'optionalDependencies', 'files', 'peerDependenciesMeta']:
    manifest.pop(field, None)
manifest.update(dependencies=versions, bundledDependencies=list(versions), os=['openharmony'], cpu=['arm64'])
(package / 'package.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
for filename in ['LICENSE', 'README.md']:
    shutil.copyfile(root / filename, package / filename)
shutil.copyfile(root / 'ohos/README.md', package / 'README.ohos.md')
shutil.copyfile(root / 'ohos/SOURCES.json', package / 'SOURCES.json')
copy_tree(root / 'tpr/licenses', package / 'licenses')
wasm_files = list((package / 'node_modules/@img/sharp-wasm32/lib').glob('*.wasm'))
if len(wasm_files) != 1 or not wasm_files[0].read_bytes().startswith(b'\0asm\x01\0\0\0'):
    raise ValueError('invalid bundled WASM module')
for path in package.rglob('*'):
    if path.is_file():
        with path.open('rb') as stream:
            if stream.read(4) == b'\x7fELF':
                raise ValueError(f'unexpected ELF; add native signing before packaging: {path}')
host = json.loads(subprocess.check_output(['node', '-p', 'JSON.stringify({node:process.version,platform:process.platform,arch:process.arch})'], text=True))
(package / 'build-info.json').write_text(json.dumps({
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
    'upstream_commit': inputs['upstream']['commit'],
    **host,
    'runtime': f'upstream @img/sharp-wasm32 {engine["version"]}, bundled without modification',
    'signing': 'not applicable: JavaScript and WebAssembly only; no ELF binaries',
}, indent=2) + '\n')
archive = output / f'sharp-{manifest["version"]}.tgz'
with archive.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', mtime=0, filename='') as zipped:
    with tarfile.open(fileobj=zipped, mode='w|') as tar:
        for path in sorted(package.rglob('*')):
            if not path.is_file():
                continue
            info = tar.gettarinfo(str(path), 'package/' + str(path.relative_to(package)))
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ''
            info.mode = 0o644
            with path.open('rb') as data:
                tar.addfile(info, data)
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_name(archive.name + '.sha256').write_text(f'{sha}  {archive.name}\n')
print(f'BUILT {archive.name} {archive.stat().st_size} {sha}; native acceptance is required separately')
