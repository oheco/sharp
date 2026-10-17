#!/usr/bin/env python3
"""Real stdio acceptance with Node socketpairs/forks and Python FIFO controls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--package', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
package = args.package.resolve()
subprocess.run(['node', root / 'test-standard-stream-node.cjs'], check=True)
subprocess.run(['node', root / 'test-stdio.cjs', package, output / 'node'], check=True)
rows = []
with tempfile.TemporaryDirectory(prefix='sharp-fifo-', dir=os.environ['TMPDIR']) as temporary:
    for kind in ['cjs', 'esm']:
        report = Path(temporary) / (kind + '.json')
        env = dict(os.environ, SHARP_STDIO_PACKAGE=str(package), SHARP_STDIO_KIND=kind,
                   SHARP_STDIO_REPORT=str(report), SHARP_STDIO_CLOSE='', SHARP_STDIO_IO='1')
        child = subprocess.run(['node', root / 'stdio-child.cjs'], env=env,
                               input=b'sharp-wasm-stdio-input\n', stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=120)
        body = json.loads(report.read_text())
        assert child.returncode == 0, (child.returncode, body, child.stderr)
        assert child.stdout == b'sharp-wasm-stdio-fd1\n', child.stdout
        assert child.stderr == b'sharp-wasm-stdio-fd2\n', child.stderr
        assert all(row['target'].startswith('pipe:[') for row in body['metadata']), body
        assert body['image']['version'] == '0.35.5-ohos.2' and body['wasmIO']
        assert body['globalFsUnchanged'] and not body['asynchronousErrors']
        rows.append(dict(name='python-fifo-' + kind, **body))
        print('PASS python-fifo-' + kind, flush=True)
node = json.loads((output / 'node/summary.json').read_text())
summary = dict(node_cases=node['cases'], fifo_cases=len(rows), passed=node['cases'] + len(rows),
               fifo=rows, cleanup='owned temporary directories removed; children waited or timeout-killed and reaped')
(output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({key: value for key, value in summary.items() if key != 'fifo'}, indent=2))
