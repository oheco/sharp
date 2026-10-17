const assert = require('node:assert/strict');
const fs = require('node:fs');
const nodeFor = require('./standard-stream-node.cjs');
const { test } = require('node:test');

// Fakes below supply errors and proc-link text only, never fabricated fs.Stats.
function rejected(code = 'EBADF', target = 'socket:[123]') {
  const error = Object.assign(new Error('original fstat failure'), { code });
  return { error, api: { constants: fs.constants, fstatSync() { throw error; }, readlinkSync() { return target; } } };
}

test('successful real fstat is first and keeps its inode and complete mode', () => {
  const fd = fs.openSync('/dev/null', 'r');
  try {
    const expected = fs.fstatSync(fd);
    const node = nodeFor({ fstatSync: fs.fstatSync, readlinkSync() { assert.fail('readlink after successful fstat'); } }, 'openharmony', fd, '/dev/test', fs);
    assert.deepEqual(node, { id: expected.ino, mode: expected.mode, node_ops: fs, path: '/dev/test' });
  } finally { fs.closeSync(fd); }
});

test('only standard-stream socket type and positive safe inode are supplied', () => {
  for (const fd of [0, 1, 2]) {
    const { api } = rejected();
    assert.deepEqual(nodeFor(api, 'openharmony', fd, '/dev/test', fs), { id: 123, mode: fs.constants.S_IFSOCK, node_ops: fs, path: '/dev/test' });
  }
});

test('other platforms, descriptors and errors preserve the original failure', () => {
  for (const [platform, fd, code] of [['linux', 0, 'EBADF'], ['openharmony', 3, 'EBADF'], ['openharmony', -1, 'EBADF'], ['openharmony', 0.5, 'EBADF'], ['openharmony', 0, 'EACCES'], ['openharmony', 0, 'EIO']]) {
    const { error, api } = rejected(code);
    api.readlinkSync = () => assert.fail('fallback outside the supported case');
    assert.throws(() => nodeFor(api, platform, fd, '', fs), e => e === error);
  }
});

test('non-sockets, unsafe/zero inode and non-exact proc text remain failures', () => {
  for (const target of ['pipe:[123]', '/dev/null', 'socket:[0]', 'socket:[-1]', 'socket:[1.5]', 'socket:[9007199254740992]', 'socket:[1]suffix', ' socket:[1]', 'socket:[1]\n', 'socket:[]']) {
    const { error, api } = rejected('EBADF', target);
    assert.throws(() => nodeFor(api, 'openharmony', 0, '', fs), e => e === error, target);
  }
});

test('missing or inaccessible proc link preserves fstat error', () => {
  for (const code of ['ENOENT', 'EACCES']) {
    const { error, api } = rejected();
    api.readlinkSync = () => { throw Object.assign(new Error('link failed'), { code }); };
    assert.throws(() => nodeFor(api, 'openharmony', 0, '', fs), e => e === error);
  }
});
