// Isolated acceptance child. The test-only loader export never enters a package.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const report = process.env.SHARP_STDIO_REPORT;
const result = { kind: process.env.SHARP_STDIO_KIND, metadata: [], asynchronousErrors: [] };
const originalFs = Object.fromEntries(Object.entries(fs).filter(([, value]) => typeof value === 'function'));
function recordError(e) { return { name: e.name, code: e.code, errno: e.errno, message: e.message }; }
process.on('unhandledRejection', e => result.asynchronousErrors.push(recordError(e)));

function ioModule(probe) {
  const str = s => [s.length, ...Buffer.from(s)];
  const section = (id, bytes) => [id, bytes.length, ...bytes];
  const body = index => [0, 0x20, 0, 0x20, 1, 0x20, 2, 0x20, 3, 0x10, index, 0x0b];
  const bodies = [body(0), body(1)];
  const bytes = [0, 97, 115, 109, 1, 0, 0, 0,
    ...section(1, [1, 0x60, 4, 0x7f, 0x7f, 0x7f, 0x7f, 1, 0x7f]),
    ...section(2, [2, ...str('io'), ...str('read'), 0, 0, ...str('io'), ...str('write'), 0, 0]),
    ...section(3, [2, 0, 0]),
    ...section(7, [2, ...str('read'), 0, 2, ...str('write'), 0, 3]),
    ...section(10, [2, ...bodies.flatMap(b => [b.length, ...b])])];
  return new WebAssembly.Instance(new WebAssembly.Module(Uint8Array.from(bytes)), { io: { read: probe.read, write: probe.write } }).exports;
}

async function main() {
  const packageRoot = process.env.SHARP_STDIO_PACKAGE;
  if (process.connected) {
    const request = await new Promise(resolve => process.once('message', resolve));
    assert.equal(request, 'sharp-stdio-ipc-request');
    await new Promise((resolve, reject) => process.send('sharp-stdio-ipc-ack', error => error ? reject(error) : resolve()));
    result.ipcRoundTrip = true;
  }
  const pythonFile = report + '.python.json';
  const python = spawnSync('python3', ['-c', 'import os,json,stat,sys\nr=[]\nfor fd in range(3):\n s=os.fstat(fd);r.append(dict(fd=fd,mode=s.st_mode,type=stat.S_IFMT(s.st_mode),ino=s.st_ino))\nwith open(sys.argv[1],"w") as f:json.dump(r,f)', pythonFile], { stdio: [0, 1, 2], timeout: 30000 });
  result.pythonProcess = { status: python.status, signal: python.signal, error: python.error && recordError(python.error) };
  assert.equal(python.status, 0, JSON.stringify(result.pythonProcess));
  const independent = JSON.parse(fs.readFileSync(pythonFile, 'utf8'));
  for (const fd of [0, 1, 2]) {
    const row = { fd, python: independent[fd] };
    row.target = fs.readlinkSync(`/proc/self/fd/${fd}`);
    try { const stat = fs.fstatSync(fd); row.stat = { ino: stat.ino, mode: stat.mode }; }
    catch (e) { row.fstatError = e.code; }
    try { fs.statSync(`/proc/self/fd/${fd}`); row.procStat = 'success'; }
    catch (e) { row.procStatError = e.code; }
    if (row.target.startsWith('socket:')) {
      assert.match(row.target, /^socket:\[(\d+)\]$/);
      assert.equal(Number(/^socket:\[(\d+)\]$/.exec(row.target)[1]), row.python.ino);
      assert.equal(row.python.type, fs.constants.S_IFSOCK);
      assert.equal(row.fstatError, 'EBADF');
      assert.equal(row.procStatError, 'ENOENT');
    } else {
      assert.equal(row.stat.ino, row.python.ino);
      assert.equal(row.stat.mode, row.python.mode);
    }
    result.metadata.push(row);
  }
  if (process.env.SHARP_STDIO_CLOSE) {
    const fd = Number(process.env.SHARP_STDIO_CLOSE);
    fs.closeSync(fd);
    assert.throws(() => fs.fstatSync(fd), { code: 'EBADF' });
    assert.throws(() => fs.readlinkSync(`/proc/self/fd/${fd}`), { code: 'ENOENT' });
    result.closed = fd;
  }
  try {
    const sharp = result.kind === 'esm' ? (await import(pathToFileURL(path.join(packageRoot, 'dist/index.mjs')))).default : require(packageRoot);
    const raw = Buffer.from([255,0,0, 0,255,0, 0,0,255, 255,255,0, 255,0,255, 0,255,255]);
    const png = await sharp(raw, { raw: { width: 3, height: 2, channels: 3 } }).png().toBuffer();
    const decoded = await sharp(png).raw().toBuffer();
    assert.deepEqual(decoded, raw);
    const rotated = await sharp(png).rotate(90).raw().toBuffer({ resolveWithObject: true });
    assert.equal(rotated.info.width, 2); assert.equal(rotated.info.height, 3);
    assert.deepEqual(rotated.data, Buffer.from([255,255,0, 255,0,0, 255,0,255, 0,255,0, 0,255,255, 0,0,255]));
    result.image = { version: sharp.versions.sharp, vips: sharp.versions.vips, pngBytes: png.length, roundTripBytes: raw.length, rotatedWidth: 2, rotatedHeight: 3 };
    if (process.env.SHARP_STDIO_IO === '1') {
      const filename = path.join(packageRoot, 'node_modules/@img/sharp-wasm32/lib/sharp-wasm32-0.35.5.node.js');
      const loader = new Module(filename, module);
      loader.filename = filename; loader.paths = Module._nodeModulePaths(path.dirname(filename));
      loader._compile(fs.readFileSync(filename, 'utf8') + '\nmodule.exports.__probe={FS,NODERAWFS,read:_fd_read,write:_fd_write,heap:()=>{growMemViews();return HEAPU8},alloc:n=>_malloc(n),free:p=>_free(p)};', filename);
      const probe = loader.exports.__probe;
      result.nodes = [0,1,2].map(fd => { const s = probe.FS.getStreamChecked(fd); return { fd, id: s.node.id, mode: s.node.mode, keys: Object.keys(s.node).sort() }; });
      for (const node of result.nodes) {
        const row = result.metadata[node.fd];
        assert.equal(node.id, row.python.ino);
        assert.equal(node.mode, row.target.startsWith('socket:') ? row.python.type : row.python.mode);
        assert.deepEqual(node.keys, ['id', 'mode', 'node_ops', 'path']);
        if (row.target.startsWith('socket:')) assert.throws(() => probe.NODERAWFS.fstat(node.fd), { code: 'EBADF' });
      }
      // Real WASM instructions invoke this engine's WASI read/write imports and
      // use the engine's actual linear memory and NODERAWFS descriptor table.
      const io = ioModule(probe);
      const pointer = probe.alloc(256);
      try {
        const vector = length => { const heap = probe.heap(); const view = new DataView(heap.buffer); view.setUint32(pointer, pointer + 32, true); view.setUint32(pointer + 4, length, true); view.setUint32(pointer + 16, 0, true); return view; };
        vector(64);
        assert.equal(io.read(0, pointer, 1, pointer + 16), 0);
        const readBytes = new DataView(probe.heap().buffer).getUint32(pointer + 16, true);
        const text = Buffer.from(probe.heap().subarray(pointer + 32, pointer + 32 + readBytes)).toString();
        assert.equal(text, 'sharp-wasm-stdio-input\n');
        result.wasmIO = { stdin: text, writes: [] };
        for (const fd of [1, 2]) {
          const text = `sharp-wasm-stdio-fd${fd}\n`; const bytes = Buffer.from(text);
          vector(bytes.length); probe.heap().set(bytes, pointer + 32);
          assert.equal(io.write(fd, pointer, 1, pointer + 16), 0);
          assert.equal(new DataView(probe.heap().buffer).getUint32(pointer + 16, true), bytes.length);
          result.wasmIO.writes.push({ fd, bytes: bytes.length });
        }
      } finally { probe.free(pointer); }
    }
  } catch (e) { result.rejection = recordError(e); }
  await new Promise(resolve => setTimeout(resolve, 30));
  result.globalFsUnchanged = Object.entries(originalFs).every(([key, value]) => fs[key] === value);
  assert.equal(result.globalFsUnchanged, true);
  fs.writeFileSync(report, JSON.stringify(result, null, 2) + '\n');
  if (process.connected) process.disconnect();
  // Failed Emscripten initialization may retain runtime handles. The negative
  // fixture has durably recorded both failures before explicitly ending itself.
  if (result.closed !== undefined) process.exit(result.image ? 4 : 0);
  process.exitCode = result.image && !result.rejection ? 0 : 2;
}
main().catch(e => { fs.writeFileSync(report, JSON.stringify({ ...result, fatal: e.stack }, null, 2) + '\n'); if (process.connected) process.disconnect(); process.exitCode = 3; });
