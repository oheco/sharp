const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const root = path.resolve(process.argv[2]);
const sharp = require(root);
(async () => {
  assert.equal(require(path.join(root, 'package.json')).version, '0.35.3-ohos.1');
  const esm = (await import(pathToFileURL(path.join(root, 'dist/index.mjs')))).default;
  const png = await sharp({ create: { width: 16, height: 12, channels: 4, background: '#ff0000' } }).png().toBuffer();
  assert.equal((await esm(png).metadata()).width, 16);
  for (const format of ['jpeg', 'png', 'webp']) {
    const output = await sharp(png).resize(8, 6).toFormat(format).toBuffer();
    const metadata = await sharp(output).metadata();
    assert.equal(metadata.width, 8);
    assert.equal(metadata.height, 6);
    assert.equal(metadata.format, format);
  }
  const { data, info } = await sharp(png).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  assert.equal(info.channels, 3);
  assert.deepEqual([...data.subarray(0, 3)], [255, 0, 0]);
  await assert.rejects(sharp(Buffer.from('not an image')).metadata());
  console.log('PASS HarmonyOS sharp WASM: CJS/ESM, PNG/JPEG/WebP, metadata, resize, pixels and invalid input');
})().catch(error => { console.error(error); process.exitCode = 1; });
