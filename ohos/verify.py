#!/usr/bin/env python3
"""Offline native release acceptance, reproducibility and upstream unit tests."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import re
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tarfile
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--reuse-builds', type=Path, help='development only: reuse two existing builds while debugging acceptance')
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, npm_config_offline='true', HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9', ALL_PROXY='http://127.0.0.1:9')


def run(command, name, cwd=root, check=True, input_text=None):
    print('+', ' '.join(map(str, command)), flush=True)
    with (output / f'{name}.log').open('w') as log:
        result = subprocess.Popen(list(map(str, command)), cwd=cwd, env=env, text=True,
                                  stdin=subprocess.DEVNULL if input_text is None else subprocess.PIPE,
                                  stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            result.communicate(input=input_text, timeout=600 if name.startswith('upstream-') else None)
        except subprocess.TimeoutExpired:
            # Node --test owns a child process: kill the owned group, not only its runner.
            try:
                os.killpg(result.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            result.communicate()
            raise RuntimeError(f'{name} timed out; owned process group killed and runner reaped') from None
    if check and result.returncode:
        raise RuntimeError(f'{name} failed ({result.returncode}); see {output / (name + ".log")}')
    return result.returncode


for script in sorted((root / 'ohos').glob('*.py')):
    ast.parse(script.read_text(), filename=str(script))
run(['git', 'diff', '--check'], 'diff-check')
builds = args.reuse_builds.resolve() if args.reuse_builds else output
if not args.reuse_builds:
    def build(name):
        return run(['python3', root / 'ohos/build.py', '--output', builds / name], name)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(build, ['build-1', 'build-2']))
archive_name = 'sharp-' + json.loads((root / 'package.json').read_text())['version'] + '.tgz'
archive = builds / 'build-1' / archive_name
assert archive.read_bytes() == (builds / 'build-2' / archive_name).read_bytes(), 'non-reproducible package'
for file in [root / 'ohos/test.cjs', *(builds / 'build-1/package/dist').glob('*.cjs'), *(builds / 'build-1/package/dist').glob('*.mjs')]:
    run(['node', '--check', file], 'syntax-' + file.name)
run(['python3', '-B', root / 'ohos/test-wasm-stdio.py'], 'loader-patch-regression')
run(['python3', '-B', root / 'ohos/test-stdio.py', '--package', builds / 'build-1/package', '--output', output / 'stdio-matrix'], 'stdio-matrix')
run(['node', root / 'ohos/test.cjs', builds / 'build-1/package'], 'native-direct')
eval_code = "const assert=require('node:assert/strict'); const sharp=require(process.argv[1]); sharp({create:{width:4,height:3,channels:3,background:'red'}}).png().toBuffer().then(async b=>assert.equal((await sharp(b).metadata()).height,3)).catch(e=>{console.error(e);process.exitCode=1});"
run(['node', '-e', eval_code, builds / 'build-1/package'], 'native-eval')
run(['node', '-', builds / 'build-1/package'], 'native-stdin', input_text=eval_code.replace('process.argv[1]', 'process.argv[2]'))
run(['node', '--input-type=module', '-e', "import {pathToFileURL} from 'node:url'; const {default:sharp}=await import(pathToFileURL(process.argv[1]+'/dist/index.mjs')); if(sharp.versions.vips!=='8.18.7') throw Error('wrong engine')", builds / 'build-1/package'], 'native-esm-eval')
base = Path(os.environ['TMPDIR']).resolve()
temporary = Path(tempfile.mkdtemp(prefix='sharp-0.35.5 acceptance ', dir=base)).resolve()
assert temporary.parent == base and temporary.name.startswith('sharp-0.35.5 acceptance ')
try:
    with tarfile.open(archive) as tar:
        tar.extractall(temporary / 'relocated package', filter='data')
    relocated = temporary / 'relocated package/package'
    run(['node', root / 'ohos/test.cjs', relocated], 'native-relocated')
    project = temporary / 'npm project'
    project.mkdir()
    env['npm_config_cache'] = str(output / 'npm-cache')
    run(['npm', 'install', '--offline', '--ignore-scripts', '--no-audit', '--no-fund', '--package-lock=false', '--prefix', project, archive], 'npm-offline-install')
    run(['node', root / 'ohos/test.cjs', project / 'node_modules/sharp'], 'native-npm-installed')
    upstream = temporary / 'upstream tests'
    shutil.copytree(relocated, upstream)
    shutil.copyfile(root / 'package.json', upstream / 'package.json')
    test_archive = temporary / 'upstream-tests.tar'
    with test_archive.open('wb') as stream:
        subprocess.run(['git', '-c', 'http.proxy=socks5h://127.0.0.1:10808', 'archive', '--format=tar', 'HEAD', 'test'], cwd=root, env=dict(env, GIT_NO_LAZY_FETCH='1'), stdout=stream, check=True)
    with tarfile.open(test_archive) as tar:
        tar.extractall(upstream, filter='data')
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
    # Keep Node's normal isolated test children, including their real socket
    # standard streams, so the suite exercises the runtime initialization fix.
    def upstream_test(file):
        code = run(['node', '--test', '--test-reporter=tap', file], 'upstream-' + file.name, cwd=upstream, check=False)
        text = (output / ('upstream-' + file.name + '.log')).read_text()
        counts = {key: sum(map(int, re.findall(r'^# ' + key + r' (\d+)$', text, re.M))) for key in ['tests', 'pass', 'fail', 'skipped', 'cancelled']}
        return {'file': file.name, 'exit_code': code, **counts}
    with ThreadPoolExecutor(max_workers=2) as workers:
        unit_results = list(workers.map(upstream_test, tests))
    (output / 'upstream-results.json').write_text(json.dumps(unit_results, indent=2) + '\n')
    result = int(any(item['exit_code'] for item in unit_results))
    summary = {
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'archive': str(archive),
        'size': archive.stat().st_size,
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'reproducible_builds': True,
        'native_direct': 'passed',
        'native_relocated': 'passed',
        'stdio_matrix': json.loads((output / 'stdio-matrix/summary.json').read_text()),
        'upstream_unit_exit': result,
        'upstream_files': len(unit_results),
        'upstream_counts': {key: sum(item[key] for item in unit_results) for key in ['tests', 'pass', 'fail', 'skipped', 'cancelled']},
        'development_reused_builds': bool(args.reuse_builds),
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)
    if result:
        raise RuntimeError(f'upstream tests failed; inspect {output / "upstream-results.json"}')
finally:
    assert temporary.resolve().parent == base and temporary.name.startswith('sharp-0.35.5 acceptance ')
    shutil.rmtree(temporary)
print('PASS offline build, JS syntax, reproducibility, relocated native acceptance and upstream unit suite')
