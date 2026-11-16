import tempfile
import unittest
from pathlib import Path
from atlas.library import index_library,search_library

class CompoundAliasTests(unittest.TestCase):
    def test_full_english_alias_finds_chinese_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'report.md';p.write_text('盛美上海 电镀 1500 腔')
            index_library([p],root/'local',{})
            aliases={'acm_shanghai':['ACM Research Shanghai','盛美上海']}
            self.assertEqual(len(search_library('ACM Research Shanghai 1500',root/'local',aliases)),1)
    def test_phrase_split_by_pdf_whitespace(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'report.md';p.write_text('Ultra ECP\n 3d 铜填充')
            index_library([p],root/'local',{})
            aliases={'ultra':['Ultra ECP 3d']}
            self.assertEqual(len(search_library('Ultra ECP 3d',root/'local',aliases)),1)

if __name__=='__main__':unittest.main()


class CoverageGapsPatterns(unittest.TestCase):
    """The locator must respect qualifier wording and not fire on unrelated prose."""

    def test_stock_pattern_matches_drifted_wording(self):
        import re
        from atlas.cli import GAP_TERMS, GAP_NUM, GAP_UNIT
        pat = re.compile(GAP_TERMS['stock'] + r'[^。；]{0,30}?' + GAP_NUM + r'\s*' + GAP_UNIT)
        # the same concept across four filings that word it differently
        for text in ['CCP刻蚀设备累计装机量超过5000反应台',
                     'ICP刻蚀设备在客户端的累计安装数达到1800个反应台',
                     '薄膜设备累计出货量已突破300个反应台',
                     '公司设备累计付运台数达2654个反应台']:
            self.assertIsNotNone(pat.search(text), text)

    def test_stock_pattern_ignores_unquantified_prose(self):
        import re
        from atlas.cli import GAP_TERMS, GAP_NUM, GAP_UNIT
        pat = re.compile(GAP_TERMS['stock'] + r'[^。；]{0,30}?' + GAP_NUM + r'\s*' + GAP_UNIT)
        self.assertIsNone(pat.search('公司装机量持续增长，客户认可度不断提升'))

    def test_customer_pattern_matches_line_counts(self):
        import re
        from atlas.cli import GAP_NUM, GAP_CUST
        pat = re.compile(GAP_NUM + r'\s*' + GAP_CUST)
        self.assertIsNotNone(pat.search('在客户73条生产线全面量产'))
        self.assertIsNotNone(pat.search('产品已进入约100条芯片制造厂生产线'))


class DuplicateDetection(unittest.TestCase):
    """Identifier uniqueness is enforced elsewhere; this finds one claim under two identifiers."""

    def test_reports_a_semantic_duplicate(self):
        import copy
        from atlas.cli import duplicates
        from atlas.core import load, ROOT
        data = load(ROOT)
        base = next(iter(data['observations'].values()))
        twin = copy.deepcopy(base)
        twin['observation_id'] = base['observation_id'] + '-TWIN'
        data['observations'][twin['observation_id']] = twin
        import atlas.cli as cli
        real = cli.load
        try:
            cli.load = lambda *a, **k: data
            out = cli.duplicates()
        finally:
            cli.load = real
        pairs = [g for g in out['groups'] if twin['observation_id'] in g['observation_ids']]
        self.assertEqual(len(pairs), 1)
        self.assertIn(base['observation_id'], pairs[0]['observation_ids'])

    def test_a_restatement_across_vintages_is_not_flagged(self):
        """An issuer restating a figure in a later report is evidence, not a duplicate."""
        import copy
        from atlas.core import load, ROOT
        import atlas.cli as cli
        data = load(ROOT)
        base = next(o for o in data['observations'].values() if o.get('reporting_basis') == 'original')
        twin = copy.deepcopy(base)
        twin['observation_id'] = base['observation_id'] + '-RESTATED'
        twin['reporting_basis'] = 'restated'
        data['observations'][twin['observation_id']] = twin
        real = cli.load
        try:
            cli.load = lambda *a, **k: data
            out = cli.duplicates()
        finally:
            cli.load = real
        self.assertFalse([g for g in out['groups'] if twin['observation_id'] in g['observation_ids']])
