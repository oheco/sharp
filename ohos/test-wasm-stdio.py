"""Reject loader version drift and repeated application before writing output."""
from pathlib import Path
import tempfile
import os
import unittest
from wasm_stdio import ORIGINAL, REPLACEMENT, patch_loader

ROOT = Path(__file__).resolve().parent.parent


class ExactLoaderPatch(unittest.TestCase):
    def test_one_fragment_preserves_surroundings(self):
        with tempfile.TemporaryDirectory(prefix='sharp-patch-', dir=os.environ['TMPDIR']) as directory:
            package = Path(directory)
            loader = package / 'node_modules/@img/sharp-wasm32/lib/sharp-wasm32-0.35.5.node.js'
            loader.parent.mkdir(parents=True)
            loader.write_text('before;' + ORIGINAL + 'after;')
            record = patch_loader(package, ROOT)
            self.assertEqual(loader.read_text(), 'before;' + REPLACEMENT + 'after;')
            self.assertEqual(record['fragment_count'], 1)
            self.assertFalse(record['wasm_modified'])
            self.assertEqual(loader.with_name('ohos-standard-stream-node.cjs').read_bytes(), (ROOT / 'ohos/standard-stream-node.cjs').read_bytes())

    def test_missing_duplicate_and_already_patched_fragments_are_rejected(self):
        for text in ['unrecognized loader', ORIGINAL + ORIGINAL, REPLACEMENT, ORIGINAL + REPLACEMENT]:
            with self.subTest(text=text), tempfile.TemporaryDirectory(prefix='sharp-patch-', dir=os.environ['TMPDIR']) as directory:
                package = Path(directory)
                loader = package / 'node_modules/@img/sharp-wasm32/lib/sharp-wasm32-0.35.5.node.js'
                loader.parent.mkdir(parents=True)
                loader.write_text(text)
                with self.assertRaisesRegex(ValueError, 'exactly one original'):
                    patch_loader(package, ROOT)
                self.assertEqual(loader.read_text(), text)
                self.assertFalse(loader.with_name('ohos-standard-stream-node.cjs').exists())


if __name__ == '__main__':
    unittest.main()
