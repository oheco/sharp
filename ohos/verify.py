#!/usr/bin/env python3
"""Offline native release acceptance, reproducibility and upstream unit tests."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, npm_config_offline='true', HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9', ALL_PROXY='http://127.0.0.1:9')


def run(command, name, cwd=root, check=True):
    print('+', ' '.join(map(str, command)), flush=True)
    with (output / f'{name}.log').open('w') as log:
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    if check and result.returncode:
        raise RuntimeError(f'{name} failed ({result.returncode}); see {output / (name + ".log")}')
    return result.returncode


for name in ['build.py', 'verify.py']:
    ast.parse((root / 'ohos' / name).read_text(), filename=name)
run(['git', 'diff', '--check'], 'diff-check')
for name in ['build-1', 'build-2']:
    run(['python3', root / 'ohos/build.py', '--output', output / name], name)
archive_name = 'sharp-0.35.5-ohos.1.tgz'
archive = output / 'build-1' / archive_name
assert archive.read_bytes() == (output / 'build-2' / archive_name).read_bytes(), 'non-reproducible package'
for file in [root / 'ohos/test.cjs', *(output / 'build-1/package/dist').glob('*.cjs'), *(output / 'build-1/package/dist').glob('*.mjs')]:
    run(['node', '--check', file], 'syntax-' + file.name)
run(['node', root / 'ohos/test.cjs', output / 'build-1/package'], 'native-direct')
base = Path(os.environ['TMPDIR']).resolve()
temporary = Path(tempfile.mkdtemp(prefix='sharp-0.35.5 acceptance ', dir=base)).resolve()
assert temporary.parent == base and temporary.name.startswith('sharp-0.35.5 acceptance ')
try:
    with tarfile.open(archive) as tar:
        tar.extractall(temporary / 'relocated package', filter='data')
    relocated = temporary / 'relocated package/package'
    run(['node', root / 'ohos/test.cjs', relocated], 'native-relocated')
    upstream = temporary / 'upstream tests'
    shutil.copytree(relocated, upstream)
    shutil.copyfile(root / 'package.json', upstream / 'package.json')
    shutil.copytree(root / 'test', upstream / 'test')
    inputs = json.loads((root / 'ohos/SOURCES.json').read_text())
    for entry in inputs['test_dependencies']:
        target = upstream / 'node_modules' / entry['name']
        target.mkdir(parents=True)
        with tarfile.open(root / entry['archive']) as tar:
            for member in tar:
                path = Path(member.name)
                assert path.parts[0] == 'package' and '..' not in path.parts
                if member.isdir():
                    continue
                assert member.isfile()
                dest = target.joinpath(*path.parts[1:])
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, dest.open('wb') as out:
                    shutil.copyfileobj(source, out)
    tests = sorted((upstream / 'test/unit').glob('*'))
    result = run(['node', '--test', '--test-reporter=tap', '--test-concurrency=2', '--test-timeout=60000', *tests], 'upstream-unit', cwd=upstream, check=False)
    summary = {
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'archive': str(archive),
        'size': archive.stat().st_size,
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'reproducible_builds': True,
        'native_direct': 'passed',
        'native_relocated': 'passed',
        'upstream_unit_exit': result,
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)
    if result:
        raise RuntimeError(f'upstream tests failed; inspect {output / "upstream-unit.log"}')
finally:
    assert temporary.resolve().parent == base and temporary.name.startswith('sharp-0.35.5 acceptance ')
    shutil.rmtree(temporary)
print('PASS offline build, JS syntax, reproducibility, relocated native acceptance and upstream unit suite')
