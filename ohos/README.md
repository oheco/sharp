# HarmonyOS ARM64 sharp

Version `0.35.3-ohos.1` uses upstream sharp 0.35.3 and its official `@img/sharp-wasm32` engine. HarmonyOS selects WASM explicitly. It runs inside the installed Node.js runtime; this package does not contain a newly compiled native libvips port. PNG, JPEG and WebP image handling used by Harness is covered by `test.cjs`. Node.js 24.21.0 is the native acceptance runtime.

## Offline build and native acceptance

Prepare Node.js 24 and Python 3. All runtime npm archives are checked into `tpr/npm`. `SOURCES.json` records exact versions, upstream URLs, licenses and SHA-256. The build verifies them, builds `dist` from this branch's JavaScript source with upstream `scripts/build.mjs`, and includes the fixed dependency closure and its license files. No npm scripts or downloads run during build or installation.

```sh
python3 ohos/build.py --output out/release-1
```

The output directory must be new. On the HarmonyOS host, run:

```sh
node ohos/test.cjs out/release-1/package
```

Repeat this test after extracting the tgz into an independent directory with spaces before release. The package contains JavaScript and WebAssembly, so it needs no ELF signing. Build information records the source commit and build Node.js version.

## Installation and use

```sh
oo update
oo install sharp
node -e "require('sharp')({create:{width:8,height:8,channels:3,background:'red'}}).png().toFile('red.png')"
```

Installation targets the current npm project. The bundled upstream packages are unmodified; they retain their own copyright and license files. The WASM package records its component versions and third-party licensing; corresponding build sources and recipes are maintained at https://github.com/lovell/sharp and https://github.com/lovell/sharp-libvips (libvips distribution 1.3.2, libvips 8.18.3).

WASM has upstream limitations, including its memory ceiling and lack of native text rendering. Performance and available formats differ from native libvips. Check `sharp.format` for engine capabilities; this port's acceptance covers PNG, JPEG, WebP, resize, raw pixels, ESM/CJS loading, and invalid input. It does not claim every sharp codec or API has been accepted on HarmonyOS.
