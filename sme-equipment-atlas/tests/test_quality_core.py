"""Adversarial core regressions: temporary fixtures, never production writes."""
import copy
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from atlas.core import ROOT, ValidationError, load, validate, validate_observation, build, snapshot

from tests.evidence_fixtures import bind_synthetic

class QualityCoreTests(unittest.TestCase):
    def test_annual_quarter_and_fiscal_lengths(self):
        data=load()
        for start,end,kind,valid in [('2023-12-31','2023-12-31','annual',False),('2024-01-01','2024-12-31','annual',True),('2023-07-01','2024-06-30','annual',True),('2023-01-01','2024-01-06','annual',True),('2024-01-01','2024-03-31','quarter',True),('2024-01-01','2024-06-30','quarter',False)]:
            o=copy.deepcopy(data['observations']['A2023-ER']);o['period'].update(start=start,end=end,kind=kind)
            if valid:validate_observation(o,data)
            else:
                with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_multi_year_flow_preserves_reporting_interval(self):
        data=load();o=copy.deepcopy(data['observations']['A2023-ER'])
        o['period'].update(start='2020-01-01',end='2023-06-30',kind='multi_year')
        validate_observation(o,data)
        for kind,end in [('annual','2023-06-30'),('multi_year','2020-12-31')]:
            with self.subTest(kind=kind,end=end):
                o['period'].update(kind=kind,end=end)
                with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_different_multi_year_durations_not_comparable(self):
        d=load();s=next(s for s in d['series'] if s['series_id']=='amec_etch_revenue')
        for oid in s['observation_ids']:
            o=d['observations'][oid];year=int(o['period']['end'][:4])
            o['period'].update(kind='multi_year',start=f'{year-2}-01-01')
        d['observations'][s['observation_ids'][-1]]['period']['start']='2010-01-01'
        with self.assertRaisesRegex(ValidationError,'incompatible interval durations'):validate(d)

    def test_revision_dimensions_preserved(self):
        d=load();d['observations']['N2024-CR-R']['dimensions']['geography']='mainland_china'
        with self.assertRaises(ValidationError):validate(d)

    def test_review_dates_validated(self):
        d=load();d['observations']['A2023-ER']['evidence']['review_date']='not-a-date'
        with self.assertRaises(ValueError):validate(d)

    def test_category_cycle(self):
        d=load();d['categories']['etch']['parent_category_id']='etch_icp'
        with self.assertRaises(ValidationError):validate(d)

    def test_interim_durations_not_comparable(self):
        d=load();s=next(s for s in d['series'] if s['series_id']=='amec_etch_revenue')
        for oid in s['observation_ids']:
            o=d['observations'][oid];o['period'].update(kind='interim',end=o['period']['end'][:4]+'-06-30')
        d['observations'][s['observation_ids'][-1]]['period']['end']='2025-09-30'
        with self.assertRaises(ValidationError):validate(d)

    def test_restricted_platform_excerpt(self):
        d=load();d['datasets']['PRIVATE']={'git_values_allowed':False}
        d['sources']['PRIVATE']={'source_id':'PRIVATE','dataset_id':'PRIVATE','sha256':'0'*64}
        p=next(iter(d['platforms'].values()));p['evidence']={'source_id':'PRIVATE','page':1,'excerpt':'Synthetic restricted excerpt','status':'pending'}
        with self.assertRaises(ValidationError):validate(d)

    def maturity(self, data, **changes):
        p=next(p for p in data['platforms'].values() if p.get('evidence'))
        row={'source_id':p['evidence']['source_id'],'page':p['evidence']['page'],
             'excerpt':'Synthetic later company disclosure','status':'pending','reviewer':'','review_date':'',
             'reported_maturity':'batch_orders','as_of':'2026-06-30','claim_kind':'company_reported',
             'notes':'Fixture milestone; not independently corroborated.'}
        row.update(changes);p['maturity_history']=[row]
        return p,row

    def test_optional_platform_maturity_history_validates(self):
        d=load();self.maturity(d);validate(d)

    def test_platform_maturity_history_rejects_bad_source(self):
        d=load();self.maturity(d,source_id='missing');
        with self.assertRaises(ValidationError):validate(d)

    def test_platform_maturity_history_dates_and_review_provenance(self):
        for changes,error in [({'as_of':'not-a-date'},ValueError),
                              ({'status':'source_checked'},ValidationError),
                              ({'status':'source_checked','reviewer':'reviewer','review_date':'bad'},ValueError)]:
            with self.subTest(changes=changes):
                d=load();self.maturity(d,**changes)
                with self.assertRaises(error):validate(d)

    def clone(self,path):
        root=path/'repo';root.mkdir()
        for name in ('atlas','data'):shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
        return root

    def test_exports_preserve_bounds_and_unselected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.clone(Path(tmp))
            for p in (root/'data/observations').glob('*.json'):
                rows=json.loads(p.read_text())
                for o in rows:
                    if o['observation_id']=='A2023-ER':o.update(relation='range',upper_value='999');bind_synthetic(o)
                p.write_text(json.dumps(rows))
            build(root)
            with (root/'build/all_observations.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            o=next(r for r in rows if r['observation_id']=='A2023-ER')
            self.assertEqual(o['upper_value'],'999');self.assertEqual(o['period_start'],'2023-01-01')
            self.assertEqual(o['reporting_scope_id'],'etch');self.assertEqual(o['evidence_status'],'source_checked')
            with (root/'build/all_observations.csv').open(encoding='utf-8-sig') as f:allrows=list(csv.DictReader(f))
            self.assertEqual(len(allrows),len(load(root)['observations']))
            self.assertTrue(any(r['selection_status']=='not_selected' for r in allrows))
            for name in ('series.csv','atlas_observations_v2.json','dependencies.json','Atlas Data View.md'):
                self.assertFalse((root/'build'/name).exists())

    def test_snapshot_rejects_unmanifested_file_and_symlink(self):
        for kind in ('file','symlink'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);root=self.clone(base);outside=base/'outside.txt';outside.write_text('fixture')
                path=root/'data/private.txt'
                if kind=='file':path.write_text('fixture')
                else:path.symlink_to(outside)
                with self.assertRaises(ValidationError):snapshot(root,base/'snapshot')
                self.assertFalse((base/'snapshot').exists())

    def test_snapshot_rebuilds(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=self.clone(base);dest=base/'snapshot'
            snapshot(root,dest)
            before=(dest/'outputs/all_observations.csv').read_bytes()
            subprocess.run([sys.executable,'-m','atlas','build'],cwd=dest,check=True,capture_output=True)
            self.assertEqual(before,(dest/'build/all_observations.csv').read_bytes())

if __name__=='__main__':unittest.main()


class ReferenceTierSegregation(unittest.TestCase):
    """Third-party reference data is recorded for context and must never compute silently."""

    def test_reference_dataset_is_refused_as_a_reconciliation_input(self):
        from atlas.core import load, reconcile, ROOT
        data = load(ROOT)
        ref = [o for o in data['observations'].values()
               if data['datasets'][o['dataset_id']]['status'] == 'reference_only']
        self.assertTrue(ref, 'expected at least one reference-tier observation')
        recipe = {'reconciliation_id': 'test', 'question': 'q', 'kind': 'ratio',
                  'numerator_id': ref[0]['observation_id'], 'denominator_id': ref[0]['observation_id']}
        result = reconcile(recipe, data)
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(any('reference market data' in r for r in result['reasons']),
                        result['reasons'])

    def test_reference_input_can_be_approved_explicitly(self):
        """The gate is a deliberate stop, not a permanent bar: an author can override it on the record."""
        from atlas.core import load, reconcile, ROOT
        data = load(ROOT)
        ref = [o for o in data['observations'].values()
               if data['datasets'][o['dataset_id']]['status'] == 'reference_only']
        recipe = {'reconciliation_id': 'test', 'question': 'q', 'kind': 'ratio',
                  'numerator_id': ref[0]['observation_id'], 'denominator_id': ref[0]['observation_id'],
                  'reference_input_approved': True}
        result = reconcile(recipe, data)
        self.assertFalse(any('reference market data' in r for r in result['reasons']), result['reasons'])

    def test_chart_data_locator_is_limited_to_the_reference_tier(self):
        import copy
        from atlas.core import load, validate, ROOT, ValidationError
        data = load(ROOT)
        sid = next((s for s, rec in data['sources'].items()
                    if rec.get('locator_kind') == 'chart_data'), None)
        self.assertIsNotNone(sid, 'expected a chart_data source')
        data = copy.deepcopy(data)
        data['datasets'][data['sources'][sid]['dataset_id']]['status'] = 'available'
        with self.assertRaises(ValidationError):
            validate(data, ROOT)


class NumericTokeniser(unittest.TestCase):
    """A sentence-final numeral must still be visible to the excerpt check."""

    def test_trailing_sentence_period_does_not_hide_a_number(self):
        from atlas.evidence import numeric_tokens
        from decimal import Decimal
        # This exact shape appears in ACM's 10-Q: "...recognized revenue for more than 390."
        self.assertIn(Decimal('390'), numeric_tokens('recognized revenue for more than 390. To date'))
        self.assertIn(Decimal('42'), numeric_tokens('total was 42.'))

    def test_decimals_are_still_parsed_whole(self):
        from atlas.evidence import numeric_tokens
        from decimal import Decimal
        self.assertIn(Decimal('42.5'), numeric_tokens('ratio 42.5 percent'))
        self.assertNotIn(Decimal('42'), numeric_tokens('ratio 42.5 percent'))


class LexicalCardinals(unittest.TestCase):
    """Written-out counts standardise to digits; vague magnitude words must not."""

    def test_chinese_cardinals_bind(self):
        from atlas.evidence import numeric_tokens
        from decimal import Decimal
        self.assertIn(Decimal('20'), numeric_tokens('超二十款新设备'))
        self.assertIn(Decimal('300'), numeric_tokens('累计出货量突破三百个反应台'))

    def test_english_cardinals_and_ordinals_bind(self):
        from atlas.evidence import numeric_tokens
        from decimal import Decimal
        self.assertIn(Decimal('2'), numeric_tokens('two tools to the U.S. facility'))
        self.assertIn(Decimal('1'), numeric_tokens('our first Ultra C Tahoe tool'))

    def test_vague_magnitudes_stay_qualitative(self):
        from atlas.evidence import numeric_tokens
        from decimal import Decimal
        # 数百 is "several hundred" and 千台级 is "thousand-unit class": neither is a count.
        for text in ('数百道工艺', '已有数十种新产品', '千台级量产应用', 'several hundred tools'):
            self.assertNotIn(Decimal('100'), numeric_tokens(text), text)
            self.assertNotIn(Decimal('1000'), numeric_tokens(text), text)

    def test_projected_clauses_are_not_bound(self):
        from atlas.evidence import numeric_tokens
        from decimal import Decimal
        self.assertNotIn(Decimal('300'), numeric_tokens('计划推出三百台'))
        self.assertNotIn(Decimal('20'), numeric_tokens('we plan to launch twenty new tools'))


class NamedCounterparties(unittest.TestCase):
    """A source that names counterparties without ranking them must not be forced into a rank."""

    def _row(self):
        import copy
        from atlas.core import load, ROOT
        data = load(ROOT)
        row = copy.deepcopy(next(o for o in data['observations'].values()
                                 if o['dimensions'].get('counterparty_bucket')))
        return data, row

    def test_named_not_ranked_requires_the_name(self):
        from atlas.core import validate_observation, ValidationError
        data, row = self._row()
        row['dimensions']['counterparty_bucket'] = 'named_not_ranked'
        row['dimensions'].pop('reported_counterparty_name', None)
        with self.assertRaises(ValidationError):
            validate_observation(row, data)

    def test_named_not_ranked_accepts_a_named_counterparty(self):
        from atlas.core import validate_observation
        data, row = self._row()
        row['dimensions']['counterparty_bucket'] = 'named_not_ranked'
        row['dimensions']['reported_counterparty_name'] = '长江存储'
        validate_observation(row, data)

    def test_two_named_counterparties_are_distinguishable(self):
        """Without the name, one customer's tool count reads as another's in every view."""
        import copy
        from atlas.core import display_scope
        data, row = self._row()
        a = copy.deepcopy(row); b = copy.deepcopy(row)
        for r, name in ((a, '长江存储'), (b, '中芯国际')):
            r['dimensions']['counterparty_bucket'] = 'named_not_ranked'
            r['dimensions']['reported_counterparty_name'] = name
        self.assertNotEqual(display_scope(a), display_scope(b))
        self.assertIn('长江存储', display_scope(a))
