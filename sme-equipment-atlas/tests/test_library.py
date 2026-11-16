import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from atlas.library import index_library, search_library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'archive'
        self.archive.mkdir()
        self.local = self.root / 'local'

    def test_dedup_aliases_and_chinese(self):
        text = '中微公司反应台累计安装超过120台'
        for name in ('generic.md', 'copy.md'):
            (self.archive / name).write_text(text)
        sha = hashlib.sha256(text.encode()).hexdigest()
        report = index_library([self.archive], self.local, {'s': {'source_id': 's', 'sha256': sha}})
        self.assertEqual(report['unique_content_hashes'], 1)
        hits = search_library('amec 累计安装', self.local)
        self.assertEqual(len(hits), 1)
        self.assertEqual(len(hits[0]['paths']), 2)
        self.assertEqual(hits[0]['source_id'], 's')
        self.assertIn('120', hits[0]['snippet'])

    def test_incremental_edit_and_removed_location(self):
        path = self.archive / 'report.txt'
        path.write_text('before')
        index_library([self.archive], self.local, [])
        with patch('atlas.library._extract', side_effect=AssertionError('cache missed')):
            self.assertEqual(index_library([self.archive], self.local, [])['cached'], 1)
        path.write_text('after!')
        self.assertEqual(index_library([self.archive], self.local, [])['extracted'], 1)
        self.assertEqual(search_library('before', self.local), [])
        self.assertEqual(len(search_library('after!', self.local)), 1)
        path.unlink()
        index_library([self.archive], self.local, [])
        self.assertEqual(search_library('after!', self.local), [])

    def test_exclude_before_open_including_symlinks(self):
        for name in ('Semis notes', '_Unsourced (do not cite)'):
            folder = self.archive / name
            folder.mkdir()
            (folder / 'secret.md').write_text('forbidden')
        (self.archive / 'alias.md').symlink_to(self.archive / 'Semis notes/secret.md')
        (self.archive / 'aliasdir').symlink_to(self.archive / 'Semis notes', target_is_directory=True)
        outside = self.root / 'outside.md'
        outside.write_text('outside')
        (self.archive / 'escape.md').symlink_to(outside)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('forbidden file opened')):
            report = index_library([self.archive, self.archive / 'alias.md'], self.local, [])
        self.assertEqual(report['catalogued_locations'], 0)
        self.assertGreaterEqual(len(report['excluded_paths']), 4)

    def test_pdf_pages_and_failed_retry(self):
        pdf = self.archive / 'AMEC.pdf'
        pdf.write_bytes(b'%PDF synthetic test fixture')
        result = subprocess.CompletedProcess([], 0, 'first page\f反应台 second page\f', '')
        with patch('atlas.library.subprocess.run', return_value=result):
            index_library([self.archive], self.local, [])
        hits = search_library('amec 反应台', self.local)
        self.assertEqual(hits[0]['page'], 2)
        self.assertNotIn('first page', hits[0]['snippet'])
        self.assertEqual(search_library('first second', self.local), [])
        pdf.write_bytes(b'%PDF different fixture')
        with patch('atlas.library.subprocess.run', side_effect=FileNotFoundError('pdftotext')):
            self.assertEqual(index_library([self.archive], self.local, [])['failures'], 1)
        with patch('atlas.library.subprocess.run', return_value=result) as run:
            self.assertEqual(index_library([self.archive], self.local, [])['failures'], 0)
            run.assert_called_once()

    def test_alias_override_literal_percent_and_limits(self):
        (self.archive / 'note.md').write_text('CustomCo precision 10%')
        index_library([self.archive], self.local, [])
        self.assertEqual(len(search_library('custom 10%', self.local, {'custom': ['CustomCo']})), 1)
        self.assertEqual(search_library('99%', self.local), [])
        with self.assertRaises(ValueError):
            search_library('', self.local)

    def test_protected_cache_symlink_rejected(self):
        protected = self.root / 'Semis notes'
        protected.mkdir()
        self.local.mkdir()
        (self.local / 'library_cache').symlink_to(protected, target_is_directory=True)
        with self.assertRaises(ValueError):
            index_library([self.archive], self.local, [])

    def test_rank_registered_original_and_direct_text(self):
        original = '华海清科 CMP 800台生产设备里程碑'
        (self.archive / 'original.txt').write_text(original)
        (self.archive / 'analysis.txt').write_text('华海清科 CMP 800台')
        (self.archive / '华海清科 800.txt').write_text('Unrelated financial prose')
        unrelated = '华海清科 finance 800000 and 1,800 and 800,000'
        (self.archive / 'numbers.txt').write_text(unrelated)
        index_library([self.archive], self.local, [
            {'source_id': 'milestone', 'sha256': hashlib.sha256(original.encode()).hexdigest()},
            {'source_id': 'finance', 'sha256': hashlib.sha256(unrelated.encode()).hexdigest()}])
        hits = search_library('华海清科 800', self.local)
        self.assertEqual(hits[0]['source_id'], 'milestone')
        self.assertFalse(any(h['source_id'] == 'finance' for h in hits))
        self.assertEqual(search_library('华海清科 800', self.local, source_ids=['milestone'])[0]['source_id'], 'milestone')
        self.assertEqual(search_library('华海清科 800', self.local, source_ids=['missing']), [])


if __name__ == '__main__':
    unittest.main()
