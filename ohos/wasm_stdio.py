"""Apply the one reviewed standard-stream initialization fragment to a private loader."""
import hashlib
from pathlib import Path
import shutil

ORIGINAL = 'var st=fs.fstatSync(i);var node={id:st.ino,mode:st.mode,node_ops:NODERAWFS,path:paths[i]};'
REPLACEMENT = 'var node=require("./ohos-standard-stream-node.cjs")(fs,process.platform,i,paths[i],NODERAWFS);'


def patch_loader(package: Path, root: Path):
    loader = package / 'node_modules/@img/sharp-wasm32/lib/sharp-wasm32-0.35.5.node.js'
    source = loader.read_bytes()
    text = source.decode('utf-8')
    count = text.count(ORIGINAL)
    if count != 1 or REPLACEMENT in text:
        raise ValueError(f'expected exactly one original NODERAWFS standard-stream fragment, found {count}')
    patched = text.replace(ORIGINAL, REPLACEMENT, 1).encode('utf-8')
    helper = loader.with_name('ohos-standard-stream-node.cjs')
    if helper.exists():
        raise ValueError('unexpected pre-existing standard-stream helper')
    shutil.copyfile(root / 'ohos/standard-stream-node.cjs', helper)
    loader.write_bytes(patched)
    return {
        'name': 'NODERAWFS standard-stream socket node metadata',
        'fragment_count': count,
        'loader': str(loader.relative_to(package)),
        'upstream_loader_sha256': hashlib.sha256(source).hexdigest(),
        'patched_loader_sha256': hashlib.sha256(patched).hexdigest(),
        'helper': str(helper.relative_to(package)),
        'helper_sha256': hashlib.sha256(helper.read_bytes()).hexdigest(),
        'wasm_modified': False,
    }
