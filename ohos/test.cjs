const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { Readable } = require('node:stream');
const { pipeline } = require('node:stream/promises');
const { test } = require('node:test');
const root = path.resolve(process.argv[2]);
const sharp = require(root);

test('HarmonyOS ARM64 and exact upstream/runtime versions', () => {
  assert.equal(process.platform, 'openharmony');
  assert.equal(process.arch, 'arm64');
  assert.equal(require(path.join(root, 'package.json')).version, '0.35.5-ohos.1');
  assert.equal(sharp.versions.sharp, '0.35.5-ohos.1');
  assert.equal(sharp.versions.vips, '8.18.7');
  assert.equal(require(path.join(root, 'node_modules/@img/sharp-wasm32/package.json')).version, '0.35.5');
});

test('CJS and ESM expose the same image API', async () => {
  const esm = (await import(pathToFileURL(path.join(root, 'dist/index.mjs')))).default;
  const png = await sharp({ create: { width: 16, height: 12, channels: 4, background: '#ff0000' } }).png().toBuffer();
  assert.equal((await esm(png).metadata()).width, 16);
});

test('Harness JPEG/PNG/WebP resize and raw RGBA pixel values', async () => {
  const raw = Buffer.alloc(16 * 12 * 4);
  for (let i = 0; i < raw.length; i += 4) raw.set([255, 0, 0, 255], i);
  const png = await sharp(raw, { raw: { width: 16, height: 12, channels: 4 } }).png().toBuffer();
  for (const format of ['jpeg', 'png', 'webp']) {
    const output = await sharp(png).resize({ width: 8, height: 6, fit: 'inside', withoutEnlargement: true }).toFormat(format).toBuffer();
    const metadata = await sharp(output).metadata();
    assert.equal(metadata.width, 8);
    assert.equal(metadata.height, 6);
    assert.equal(metadata.format, format);
  }
  const { data, info } = await sharp(png).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  assert.equal(info.channels, 3);
  assert.equal(data.length, 16 * 12 * 3);
  assert.deepEqual([...data.subarray(0, 3)], [255, 0, 0]);
});

test('Real upstream JPEG EXIF autoOrient, PNG transparency and WebP fixtures', async () => {
  const fixtures = path.join(__dirname, '../test/fixtures');
  const jpeg = await fs.readFile(path.join(fixtures, 'Landscape_6.jpg'));
  const original = await sharp(jpeg).metadata();
  assert.equal(original.orientation, 6);
  const oriented = await sharp(jpeg).autoOrient().png().toBuffer();
  const actual = await sharp(oriented).metadata();
  assert.equal(actual.width, original.height);
  assert.equal(actual.height, original.width);
  for (const [filename, format] of [['blackbug.png', 'png'], ['4.webp', 'webp']]) {
    const input = await fs.readFile(path.join(fixtures, filename));
    const output = await sharp(input).resize(48, 32, { fit: 'inside' }).toFormat(format).toBuffer();
    assert.equal((await sharp(output).metadata()).format, format);
  }
});

test('Rotation, crop, compositing and alpha pixels', async () => {
  const green = await sharp({ create: { width: 2, height: 2, channels: 4, background: '#00ff00' } }).png().toBuffer();
  const { data, info } = await sharp({ create: { width: 8, height: 6, channels: 4, background: '#ff0000' } })
    .composite([{ input: green, left: 0, top: 0 }]).raw().toBuffer({ resolveWithObject: true });
  assert.equal(info.channels, 4);
  assert.deepEqual([...data.subarray(0, 4)], [0, 255, 0, 255]);
  assert.deepEqual([...data.subarray(4 * 7, 4 * 8)], [255, 0, 0, 255]);
  const rotated = await sharp(data, { raw: info }).rotate(90).extract({ left: 0, top: 0, width: 3, height: 4 }).png().toBuffer();
  assert.equal((await sharp(rotated).metadata()).height, 4);
});

test('Concurrent pipelines and stream input/output', async () => {
  const input = await sharp({ create: { width: 24, height: 16, channels: 3, background: 'blue' } }).png().toBuffer();
  const outputs = await Promise.all(Array.from({ length: 4 }, (_, i) => sharp(input).resize(i + 2).webp().toBuffer()));
  for (let i = 0; i < outputs.length; i++) assert.equal((await sharp(outputs[i]).metadata()).width, i + 2);
  const transform = sharp().resize(6, 4).png();
  const result = transform.toBuffer();
  await pipeline(Readable.from([input]), transform);
  assert.equal((await sharp(await result).metadata()).height, 4);
});

test('File paths with spaces, Unicode names and missing inputs', async () => {
  assert.ok(process.env.TMPDIR, 'TMPDIR is required');
  const base = await fs.realpath(process.env.TMPDIR);
  const temporary = await fs.mkdtemp(path.join(base, 'sharp-0.35.5 test '));
  try {
    const file = path.join(temporary, '红色 image.png');
    await sharp({ create: { width: 9, height: 7, channels: 3, background: 'red' } }).png().toFile(file);
    assert.equal((await sharp(file).metadata()).width, 9);
    await assert.rejects(sharp(path.join(temporary, 'missing.png')).metadata(), /Input file is missing/);
  } finally {
    const resolved = await fs.realpath(temporary);
    assert.equal(path.dirname(resolved), base);
    assert.ok(path.basename(resolved).startsWith('sharp-0.35.5 test '));
    await fs.rm(resolved, { recursive: true });
  }
});

test('Invalid input, truncated data, pixel limit and parameter errors', async () => {
  await assert.rejects(sharp(Buffer.from('not an image')).metadata(), /unsupported image format/i);
  const png = await sharp({ create: { width: 16, height: 12, channels: 4, background: 'red' } }).png().toBuffer();
  await assert.rejects(sharp(png.subarray(0, 24)).toBuffer());
  await assert.rejects(sharp(png, { limitInputPixels: 10 }).toBuffer(), /pixel limit/);
  assert.throws(() => sharp(png).resize(-1), /positive integer/);
});
