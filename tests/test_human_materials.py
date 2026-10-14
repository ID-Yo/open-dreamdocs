from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import human_materials as hm
import project_memory as pm


class HumanMaterialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.materials = self.root / 'human-materials'
        self.materials.mkdir()
        self.addCleanup(self.temp.cleanup)

    def material(self, name):
        path = self.materials / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'Original synthetic bytes; not parsed.')
        return path

    def index(self, names):
        rows = ['| Material | Description / purpose | Format | Tags | Review status | Reviewed |',
                '|---|---|---|---|---|---|']
        for name in names:
            rows.append(f'| [Original]({quote(name, safe="/")}) | Filename only; content not reviewed. | binary | intake | unread | — |')
        (self.materials / 'README.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')

    def test_empty_and_housekeeping(self):
        self.index([])
        self.material('.gitignore')
        self.material('nested/.DS_Store')
        self.assertEqual(hm.check(self.root), [])

    def test_documented_example_is_not_a_material_row(self):
        self.index([])
        with (self.materials / 'README.md').open('a', encoding='utf-8') as out:
            out.write('\n```text\n| [Example](not-real.pdf) | Example only | PDF | demo | unread | — |\n```\n')
        self.assertEqual(hm.check(self.root), [])

    def test_scan_permission_error_is_reported(self):
        self.index([])
        def inaccessible(*args, **kwargs):
            kwargs['onerror'](PermissionError(13, 'Access denied', 'restricted'))
            return iter(())
        with patch.object(hm.os, 'walk', side_effect=inaccessible):
            self.assertTrue(any('Cannot inventory' in e for e in hm.check(self.root)))

    def test_nested_spaces_unicode_and_nested_readme_are_materials(self):
        names = ['slides/Plan (final) #1.pptx', 'photos/café.png', 'notes/README.md', '.hidden-source']
        paths = [self.material(n) for n in names]
        before = [p.read_bytes() for p in paths]
        self.index(names)
        self.assertEqual(hm.check(self.root), [])
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertEqual(pm.validate_links(self.root.resolve()), len(names))

    def test_add_move_remove_and_reconcile(self):
        path = self.material('old/report.pdf')
        self.index(['old/report.pdf'])
        self.assertEqual(hm.check(self.root), [])
        target = self.materials / 'new/report.pdf'
        target.parent.mkdir()
        path.rename(target)
        errors = hm.check(self.root)
        self.assertTrue(any('Missing row' in e for e in errors))
        self.assertTrue(any('Stale row' in e for e in errors))
        self.index(['new/report.pdf'])
        self.assertEqual(hm.check(self.root), [])
        target.unlink()
        self.assertTrue(any('Stale row' in e for e in hm.check(self.root)))
        self.index([])
        self.assertEqual(hm.check(self.root), [])

    def test_duplicate_and_outside_paths_rejected(self):
        self.material('one.pdf')
        self.index(['one.pdf', 'one.pdf', '../outside.pdf'])
        errors = hm.check(self.root)
        self.assertTrue(any('Duplicate' in e for e in errors))
        self.assertTrue(any('Unsafe' in e for e in errors))

    def test_review_status_and_date(self):
        self.material('one.pdf')
        self.index(['one.pdf'])
        index = self.materials / 'README.md'
        text = index.read_text(encoding='utf-8')
        index.write_text(text.replace('| unread |', '| reviewed |'), encoding='utf-8')
        self.assertTrue(any('review date' in e for e in hm.check(self.root)))
        index.write_text(text.replace('| unread |', '| unparseable |'), encoding='utf-8')
        self.assertEqual(hm.check(self.root), [])

    def test_cli_reports_missing_row_nonzero(self):
        self.index([])
        self.material('unread.bin')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/human_materials.py'),
                                 '--root', str(self.root)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing row', result.stdout)

    def test_symlink_is_not_followed(self):
        self.index([])
        outside = self.root / 'outside.txt'
        outside.write_text('private', encoding='utf-8')
        try:
            (self.materials / 'link.txt').symlink_to(outside)
        except OSError:
            self.skipTest('Host does not permit creating symlinks')
        self.assertTrue(any('symlink' in e.lower() for e in hm.check(self.root)))


if __name__ == '__main__':
    unittest.main()
