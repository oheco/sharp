# HarmonyOS ARM64 sharp

Version `0.35.5-ohos.1` is based on upstream sharp `v0.35.5`, commit `51a990faa26ade5586a4934ac9673c98d8893326`, and uses the unmodified official `@img/sharp-wasm32@0.35.5` engine (libvips 8.18.7, sharp-libvips distribution 1.3.4). HarmonyOS ARM64 explicitly selects WASM inside the installed Node.js runtime. This continues the 0.35.3 port's runtime design; it does not build native libvips or recompile the upstream WASM engine.

## Fixed inputs and offline build

Prepare the HarmonyOS Node.js 24 runtime, Python 3 and Git. Runtime archives in `tpr/npm`, test archives in `tpr/test`, and source/provenance archives in `tpr/sources` are complete unmodified upstream inputs. `ohos/SOURCES.json` records exact versions, source commits, upstream URLs, SHA256, npm SHA512, licenses and modifications. The sharp-libvips source archive preserves upstream WASM build recipes, component versions and third-party notices. Runtime dependencies retain their original license and copyright files; `tpr/licenses` adds the WASM component notices and LGPL/GPL texts to the release.

The build verifies all inputs and the transitive runtime closure, builds `dist` from this branch using the upstream JavaScript distribution script, and bundles the official engine without npm installation or downloads. It requires a clean committed tree and a new output directory. It rejects unexpected ELF binaries; the JS/WASM-only package does not need ELF signing.

```sh
python3 ohos/build.py --output "$XDG_CACHE_HOME/sharp-0.35.5/release-1"
node ohos/test.cjs "$XDG_CACHE_HOME/sharp-0.35.5/release-1/package"
```

Build information records the exact port and upstream commits, Node.js version, platform, architecture and signing applicability. Tar/gzip timestamps, ownership, file ordering and modes are normalized.

## Native acceptance

Run on HarmonyOS ARM64 with Node.js 24.21.0, Python 3, and `TMPDIR` pointing to the application's private temporary filesystem:

```sh
python3 ohos/verify.py --output "$XDG_CACHE_HOME/sharp-0.35.5/acceptance-1"
```

This performs two fresh offline builds without download calls and with deliberately unusable proxy endpoints, byte-for-byte archive comparison, Python parsing, JavaScript syntax checks, direct package acceptance, CJS/ESM eval and stdin entry points, extraction into a new temporary path containing spaces, repeated acceptance, and the upstream unit suite with pinned test dependencies. Tests use isolated copies and clean their temporary directories. Logs and the summary remain in the specified cache output. No existing sharp installation or DSH process is modified.

On this HarmonyOS Node build, `node --test` isolation children can expose invalid standard file descriptors (`fs.fstatSync(0/1/2)` reports `EBADF`), which prevents Emscripten NODERAWFS initialization. The verifier therefore launches every upstream unit file as a separate ordinary Node process with real standard streams and a per-file timeout. The engine archive remains unmodified. Applications must provide valid stdin/stdout/stderr descriptors. The upstream test adaptations add HarmonyOS to the platform whitelist and use the loaded WASM engine to distinguish 32-bit memory and Buffer transfer behavior from native ARM64.

The native acceptance tests cover exact versions and platform, CJS/ESM loading, Harness-style JPEG/PNG/WebP buffer resizing, raw RGBA pixels, real upstream fixtures and EXIF orientation, transparency, compositing, rotation/crop, concurrent pipelines, streams, filesystem/Unicode paths, missing files, invalid and truncated images, pixel limits and invalid parameters.

## Installation and use

The release archive is an npm package with one top-level `package/` directory and its complete bundled `node_modules`; no command-line entry point is declared. To use an extracted package in an isolated project, copy its `package/` directory to `node_modules/sharp`, then:

```sh
node -e "require('sharp')({create:{width:8,height:8,channels:3,background:'red'}}).png().toBuffer().then(b=>console.log(b.length))"
```

The software directory can install it into the current npm project with `oo install sharp --` after the separate catalog update. This repository does not edit the catalog or Harness. Use explicit immutable GitHub release URLs and verify the published SHA256.

WASM has upstream limitations, including its memory ceiling and lack of native text rendering. Performance and formats differ from native libvips. Query `sharp.format` for codec availability. Source recipes and licensing provenance do not imply that the upstream Emscripten toolchain or every codec was rebuilt on HarmonyOS. Native acceptance results apply to the tested host/runtime.
