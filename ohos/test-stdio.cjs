const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, fork } = require('node:child_process');

(async () => {
  const packageRoot = path.resolve(process.argv[2]);
  const output = path.resolve(process.argv[3]);
  fs.mkdirSync(output, { recursive: false });
  const temporaryBase = fs.realpathSync(process.env.TMPDIR);
  const temporary = fs.mkdtempSync(path.join(temporaryBase, 'sharp-stdio-'));
  const worker = path.join(__dirname, 'stdio-child.cjs');
  const rows = [];
  try {
    for (const kind of ['cjs', 'esm']) {
      for (const method of ['spawn', 'fork', 'eval']) {
        const modes = method === 'eval' ? ['all-socket'] : ['file', 'all-socket', 'stdin-socket', 'stdout-socket', 'stderr-socket', 'closed-0', 'closed-1', 'closed-2'];
        for (const mode of modes) {
          const name = `${method}-${mode}-${kind}`;
          const report = path.join(output, name + '.json');
          const handles = [fs.openSync(path.join(temporary, name + '.in'), 'w+'), fs.openSync(path.join(temporary, name + '.out'), 'w+'), fs.openSync(path.join(temporary, name + '.err'), 'w+')];
          fs.writeSync(handles[0], Buffer.from('sharp-wasm-stdio-input\n'), 0, Buffer.byteLength('sharp-wasm-stdio-input\n'), 0);
          const stdio = [...handles];
          if (mode === 'all-socket') stdio.fill('pipe');
          for (const [fd, which] of ['stdin', 'stdout', 'stderr'].entries()) if (mode === which + '-socket') stdio[fd] = 'pipe';
          const env = { ...process.env, SHARP_STDIO_PACKAGE: packageRoot, SHARP_STDIO_KIND: kind, SHARP_STDIO_REPORT: report, SHARP_STDIO_CLOSE: mode.startsWith('closed-') ? mode.slice(-1) : '', SHARP_STDIO_IO: mode.startsWith('closed-') ? '0' : '1' };
          if (method === 'fork') stdio.push('ipc');
          const args = method === 'eval' ? (kind === 'esm' ? ['--input-type=module', '-e', `await import(${JSON.stringify(require('node:url').pathToFileURL(worker).href)})`] : ['-e', `require(${JSON.stringify(worker)})`]) : [worker];
          const child = method === 'fork' ? fork(worker, [], { stdio, env }) : spawn(process.execPath, args, { stdio, env });
          let stdout = '', stderr = '';
          const messages = [];
          if (method === 'fork') {
            child.on('message', message => messages.push(message));
            child.send('sharp-stdio-ipc-request');
          }
          child.stdin?.on('error', e => { if (e.code !== 'EPIPE') throw e; });
          child.stdin?.end('sharp-wasm-stdio-input\n');
          child.stdout?.on('data', b => { stdout += b; }); child.stderr?.on('data', b => { stderr += b; });
          const timer = setTimeout(() => child.kill('SIGKILL'), 120000);
          let status;
          try { status = await new Promise((resolve, reject) => { child.once('error', reject); child.once('close', (code, signal) => resolve({ code, signal })); }); }
          finally { clearTimeout(timer); for (const fd of handles) fs.closeSync(fd); }
          const body = JSON.parse(fs.readFileSync(report, 'utf8'));
          assert.equal(status.code, 0, JSON.stringify({ name, ...status, ...body, stderr }));
          assert.equal(body.globalFsUnchanged, true);
          if (method === 'fork') { assert.equal(body.ipcRoundTrip, true); assert.deepEqual(messages, ['sharp-stdio-ipc-ack']); }
          if (mode.startsWith('closed-')) {
            assert.ok(body.rejection); assert.equal(body.image, undefined);
            assert.ok(body.asynchronousErrors.some(e => e.errno === 8 || e.code === 'EBADF'), name);
          } else {
            assert.equal(body.image.version, '0.35.5-ohos.2'); assert.equal(body.rejection, undefined);
            assert.equal(body.asynchronousErrors.length, 0);
          }
          if (!mode.startsWith('closed-')) {
            assert.ok(body.wasmIO);
            const actualOut = stdio[1] === 'pipe' ? stdout : fs.readFileSync(path.join(temporary, name + '.out'), 'utf8');
            const actualErr = stdio[2] === 'pipe' ? stderr : fs.readFileSync(path.join(temporary, name + '.err'), 'utf8');
            assert.equal(actualOut, 'sharp-wasm-stdio-fd1\n'); assert.equal(actualErr, 'sharp-wasm-stdio-fd2\n');
          }
          rows.push({ name, ...status, ...body, messages, stdout, stderr });
          console.log('PASS', name);
        }
      }
    }
    fs.writeFileSync(path.join(output, 'summary.json'), JSON.stringify({ cases: rows.length, passed: rows.length, rows }, null, 2) + '\n');
  } finally {
    assert.equal(path.dirname(fs.realpathSync(temporary)), temporaryBase);
    assert.ok(path.basename(temporary).startsWith('sharp-stdio-'));
    fs.rmSync(temporary, { recursive: true });
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
