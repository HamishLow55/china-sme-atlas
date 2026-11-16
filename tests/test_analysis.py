"""Reference validation, manifests and end-to-end project invariants against the pinned Atlas."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from sme_analysis import reference
from sme_analysis.cli import project_module
from sme_analysis.data import DEFAULT_ATLAS, Atlas

HAVE_ATLAS=(DEFAULT_ATLAS/'atlas/core.py').is_file()

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.orig=reference.REF
        reference.REF=Path(self.tmp.name);shutil.copytree(self.orig,reference.REF,dirs_exist_ok=True)
    def tearDown(self):reference.REF=self.orig;self.tmp.cleanup()
    def test_committed_tables_are_structurally_valid(self):
        self.assertEqual(reference.validate(),[])
    def test_unknown_group_and_assumption_and_status_are_rejected(self):
        p=reference.REF/'customs_segment_map.csv';t=pd.read_csv(p,dtype=str,keep_default_na=False)
        t.loc[0,'group_id']='nonexistent';t.loc[1,'allocation']='amount_usd:A-MISSING';t.loc[2,'status']='maybe';t.to_csv(p,index=False)
        problems='\n'.join(reference.validate())
        for needle in ('unknown group_id','unknown assumption','invalid status'):self.assertIn(needle,problems)
    def test_product_splits_must_be_ordered_and_not_exceed_the_basket(self):
        p=reference.REF/'product_splits.csv';t=pd.read_csv(p,dtype=str,keep_default_na=False)
        t.loc[0,'share_low']='0.9';t.to_csv(p,index=False)
        self.assertTrue(any('low <= base <= high' in x for x in reference.validate()))
        t=pd.read_csv(p,dtype=str,keep_default_na=False);t.loc[0,'share_low']='0.1';k=t[t.split_id.str.startswith('kingsemi-2025')].index
        t.loc[k,'share_base']='0.6';t.loc[k,'share_high']='0.7';t.to_csv(p,index=False)
        self.assertTrue(any('share_base sums above 1' in x for x in reference.validate()))
    def test_assumptions_need_a_basis(self):
        p=reference.REF/'assumptions.csv';t=pd.read_csv(p,dtype=str,keep_default_na=False);t.loc[0,'basis']='';t.to_csv(p,index=False)
        self.assertIn('assumptions: every row needs a basis',reference.validate())

@unittest.skipUnless(HAVE_ATLAS,'Atlas submodule not checked out')
class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.atlas=Atlas();cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)
        for name in ('china_share_by_segment','china_imports','hbm_step_market'):
            d=cls.out/name;d.mkdir();project_module(name).run(cls.atlas,d)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_reference_ids_resolve_in_pinned_atlas(self):
        self.assertEqual(reference.validate(self.atlas),[])
    def test_import_allocation_conserves_customs_totals(self):
        d=pd.read_csv(self.out/'china_share_by_segment/imports_by_hs8_allocation.csv',dtype={'hs8':str})
        hs=self.atlas.statistics('china_customs/imports_hs8_monthly.csv');hs['usd']=pd.to_numeric(hs['usd']);hs['year']=hs['period'].str[:4].astype(int)
        for year in (2023,2024,2025):
            for case in ('low','base','high'):
                alloc=d[(d['year']==year)&(d['case']==case)&(d['hs8']!='84861040')&~d['hs8'].str.startswith('848610')]['usd'].sum()
                self.assertAlmostEqual(alloc,hs[hs['year']==year]['usd'].sum(),delta=1)
    def test_splits_supersede_the_rows_they_cover(self):
        dom=pd.read_csv(self.out/'china_share_by_segment/domestic_revenue_by_vendor.csv',keep_default_na=False)
        self.assertFalse(dom.duplicated(['entity_id','group_id','year','in_share']).any())
        n=dom[(dom['entity_id']=='naura')&(dom['year']==2025)]
        self.assertEqual(set(n['basis']),{'split (tier C)'})
        self.assertTrue((n['value_usd_low']<=n['value_usd']).all() and (n['value_usd']<=n['value_usd_high']).all())
        h=dom[(dom['entity_id']=='hwatsing')&(dom['year']==2025)]
        self.assertEqual(set(h['group_id']),{'cmp','backend','doping'})
    def test_geography_splits_scale_named_vendors(self):
        dom=pd.read_csv(self.out/'china_share_by_segment/domestic_revenue_by_vendor.csv',keep_default_na=False)
        y=dom[(dom['entity_id']=='yitang_semiconductor')&(dom['year']==2025)]
        self.assertTrue(len(y) and y['adjustment'].str.contains('geo-yitang_semiconductor-2025').all())
    def test_share_ranges_are_ordered(self):
        t=pd.read_csv(self.out/'china_share_by_segment/segment_table.csv')
        for lo,mid,hi in (('share_min','provisional_domestic_share','share_max'),('share_with_estimates_min','share_with_estimates','share_with_estimates_max')):
            u=t.dropna(subset=[mid]);self.assertTrue(((u[lo]<=u[mid]+1e-9)&(u[mid]<=u[hi]+1e-9)).all(),lo)
        s=pd.read_csv(self.out/'hbm_step_market/step_market.csv').dropna(subset=['share_base'])
        self.assertTrue(((s['share_min']<=s['share_base']+1e-9)&(s['share_base']<=s['share_max']+1e-9)).all())
    def test_step_market_covers_every_step(self):
        s=pd.read_csv(self.out/'hbm_step_market/step_market.csv')
        self.assertTrue(set(reference.load('hbm_tool_stack')['step_id'])<=set(s['step_id']))
    def test_excluded_vendors_never_counted(self):
        dom=pd.read_csv(self.out/'china_share_by_segment/domestic_revenue_by_vendor.csv')
        excluded=set(reference.load('vendors').query("include=='no'")['entity_id'])
        self.assertFalse(set(dom['entity_id'])&excluded)
    def test_shares_are_bounded_and_coverage_below_cepea(self):
        t=pd.read_csv(self.out/'china_share_by_segment/segment_table.csv').dropna(subset=['provisional_domestic_share'])
        self.assertTrue(((t['share_min']<=t['provisional_domestic_share']+1e-9)&(t['provisional_domestic_share']<=t['share_max']+1e-9)).all())
        self.assertTrue(((t['provisional_domestic_share']>0)&(t['provisional_domestic_share']<1)).all())
        # CEPEA is a cross-check, not a ceiling (its survey can omit firms), but the floors alone should not overshoot it.
        cov=pd.read_csv(self.out/'china_share_by_segment/numerator_coverage.csv');self.assertTrue((cov['coverage_low']<1).all());self.assertTrue((cov['coverage']<1.15).all())
    def test_estimates_drop_rows_the_atlas_now_covers(self):
        est=pd.read_csv(self.out/'china_share_by_segment/estimates_layer.csv',keep_default_na=False)
        dom=pd.read_csv(self.out/'china_share_by_segment/domestic_revenue_by_vendor.csv')
        have={(e,y) for e,y in zip(dom['entity_id'],dom['year'])}
        raw=pd.concat([pd.read_csv(p,dtype=str,keep_default_na=False) for p in sorted(project_module('china_share_by_segment').ESTIMATES.glob('*.csv'))])
        lead={(u,int(y)):o.split(':')[0].strip() for u,y,o in zip(raw['unit'],raw['year'],raw['overlaps'])}
        for r in est.itertuples():
            covered=(lead[(r.unit,r.year)],r.year) in have
            self.assertEqual(bool(r.dropped),covered or raw.loc[(raw['unit']==r.unit)&(raw['year']==str(r.year)),'geography'].iloc[0]=='global',r.unit)
    def test_held_out_revenue_stays_out_of_shares(self):
        dom=pd.read_csv(self.out/'china_share_by_segment/domestic_revenue_by_vendor.csv')
        t=pd.read_csv(self.out/'china_share_by_segment/segment_table.csv')
        for (y,g),grp in dom[dom['group_id'].isin(t['group_id'])].groupby(['year','group_id']):
            row=t[(t['year']==y)&(t['group_id']==g)].iloc[0]
            self.assertAlmostEqual(row['held_out_usd_m'],grp.loc[~grp['in_share'],'value_usd'].sum()/1e6,places=3)
            if row['domestic_revenue_usd_m']==row['domestic_revenue_usd_m']:
                self.assertAlmostEqual(row['domestic_revenue_usd_m'],grp.loc[grp['in_share'],'value_usd'].sum()/1e6,places=3)
    def test_import_groups_are_ordered_ranges_and_conserve_totals(self):
        g=pd.read_csv(self.out/'china_imports/imports_by_group.csv')
        self.assertTrue(((g['usd_m_min']<=g['usd_m_base']+1e-6)&(g['usd_m_base']<=g['usd_m_max']+1e-6)).all())
        codes=pd.read_csv(self.out/'china_imports/imports_by_code.csv',dtype={'hs8':str})
        for period,grp in g.groupby('period'):
            self.assertAlmostEqual(grp['usd_m_base'].sum(),codes.loc[codes['period']==period,'usd_m'].sum(),delta=0.5)
        periods=set(g['period']);ytd={p for p in periods if ' Jan-' in p}
        self.assertEqual(periods-ytd,{'2021','2022','2023','2024','2025'})
        self.assertEqual({p[:4] for p in ytd},{'2025','2026'})
    def test_manifests_record_pinned_atlas_and_inputs(self):
        for name in ('china_share_by_segment','china_imports'):
            m=json.loads((self.out/name/'manifest.json').read_text())
            self.assertEqual(m['atlas'][0]['label'],'pinned submodule');self.assertEqual(len(m['atlas'][0]['commit']),40)
            self.assertTrue(m['atlas'][0]['inputs']);self.assertNotIn('/Users/',json.dumps(m))

class UnlistedVendorValidationTests(unittest.TestCase):
    """Synthetic firm files (test-only values) exercise the estimate contract."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name);self.mod=project_module('unlisted_vendors')
        self.groups=set(reference.load('segments')['group_id'])
        (self.d/'synthetic.md').write_text('note')
        pd.DataFrame([{'evidence_id':'s1','title':'Synthetic filing','publisher':'Test','url':'https://example.org/a','published':'2025-01-01',
            'accessed':'2026-09-24','trust_tier':'1','locator':'p1','note':''},{'evidence_id':'s2','title':'Synthetic blog','publisher':'Test',
            'url':'https://example.org/b','published':'2025-01-01','accessed':'2026-09-24','trust_tier':'4','locator':'','note':''}]).to_csv(self.d/'sources.csv',index=False)
    def tearDown(self):self.tmp.cleanup()
    def check(self,**over):
        row={'firm_id':'synthetic','unit':'line','group_id':'doping','year':'2025','revenue_cny_m_low':'60','revenue_cny_m_base':'100',
             'revenue_cny_m_high':'160','geography':'china','scope_note':'','method_tier':'D','method':'test','narrow_range_reason':'',
             'evidence_ids':'s1','overlaps':'','status':'proposed','author':'test','as_of':'2026-09-24'}
        row.update(over);pd.DataFrame([row]).to_csv(self.d/'synthetic.csv',index=False)
        return self.mod.validate_firm(self.d/'synthetic.csv',self.d/'sources.csv',self.groups,self.d)[1]
    def test_valid_row_passes(self):self.assertEqual(self.check(),[])
    def test_range_narrower_than_tier_needs_reason(self):
        self.assertTrue(any('narrower than tier D' in p for p in self.check(revenue_cny_m_low='90',revenue_cny_m_high='110')))
        self.assertEqual(self.check(revenue_cny_m_low='90',revenue_cny_m_high='110',narrow_range_reason='two independent methods agree'),[])
    def test_strong_tiers_need_tier_one_or_two_evidence(self):
        self.assertTrue(any('needs at least one trust-tier 1-2 source' in p for p in self.check(method_tier='B',revenue_cny_m_low='85',revenue_cny_m_high='115',evidence_ids='s2')))
    def test_unknown_evidence_group_and_order_are_rejected(self):
        probs='\n'.join(self.check(evidence_ids='s9',group_id='nope',revenue_cny_m_low='200'))
        for needle in ('not in sources','unknown group_id','low <= base <= high'):self.assertIn(needle,probs)

if __name__=='__main__':unittest.main()

class FxTests(unittest.TestCase):
    def test_usd_conversion(self):
        from sme_analysis.fx import usd, usd_per_unit, parse_money_unit
        self.assertEqual(usd(5,'USD',2025),5)
        self.assertTrue(0.13<usd_per_unit('CNY',2025)<0.15)
        self.assertEqual(usd_per_unit('RMB','2024 H1'),usd_per_unit('CNY',2024))
        self.assertTrue(0.0060<usd_per_unit('JPY',2024)<0.0072)
        self.assertEqual(parse_money_unit('CNY 100m'),('CNY',100,'USD m'))
        self.assertEqual(parse_money_unit('CNY'),('CNY',1,'USD'))
        self.assertEqual(parse_money_unit('JPY bn'),('JPY',1000,'USD m'))
        self.assertIsNone(parse_money_unit('units'))
        self.assertEqual(usd_per_unit('JPY','FY20'),usd_per_unit('JPY',2020))
        self.assertEqual(usd_per_unit('JPY','FY2024 (to Mar 2025)'),usd_per_unit('JPY',2024))
        with self.assertRaises(KeyError):usd_per_unit('CNY',2010)


class FitTests(unittest.TestCase):
    def test_logistic_recovers_a_known_curve(self):
        import numpy as np
        from sme_analysis.fits import logistic, logistic_fit, years_to, cagr
        t=np.arange(2016,2026);y=logistic(t,0.8,0.6,2024)
        f=logistic_fit(t,y,K=0.8);self.assertAlmostEqual(f['r'],0.6,places=4);self.assertAlmostEqual(f['t50'],2024,places=3)
        g=logistic_fit(t,y);self.assertLess(abs(g['K']-0.8),0.05);lo,hi=g['band'](2030);self.assertLessEqual(lo,hi)
        self.assertAlmostEqual(years_to(f,0.4),2024,places=3);self.assertAlmostEqual(cagr(100,121,2),0.1)
        with self.assertRaises(ValueError):logistic_fit([1,2],[0.1,0.2])


@unittest.skipUnless(HAVE_ATLAS,'needs the pinned Atlas')
class SeriesTests(unittest.TestCase):
    def test_stock_metrics_fall_back_to_as_of(self):
        from sme_analysis.series import atlas_series
        r=atlas_series(Atlas(),'cxmt','long_term_deferred_expenses')
        self.assertTrue(r['points']);self.assertTrue(all(p['period'].endswith('-12') for p in r['points']))
