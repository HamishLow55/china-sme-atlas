"""Real failure regressions plus synthetic market fixtures (not research data)."""
import copy
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from atlas.core import ROOT, ValidationError, load, validate, validate_observation, reconcile, snapshot, money
from atlas import cli

from tests.evidence_fixtures import bind_synthetic

def synthetic_market():
    data=copy.deepcopy(load())
    n=copy.deepcopy(data['observations']['A2025-ER'])
    n.update(observation_id='TEST-N',value='100',unit='CNY',precision='as_reported',relation='eq')
    n['dimensions']['geography']='China'
    n['dimensions']['geography_basis']='customer_fab_location'
    n['dimensions']['service_scope']='equipment_only'
    d=copy.deepcopy(n)
    d.update(observation_id='TEST-D',value='200',entity_id='market',metric_id='market_size',dataset_id='TEST-ANALYST',source_id='TEST-SOURCE',claim_kind='analyst_estimate',market_definition_id='TEST-CHINA-ETCH')
    data['datasets']['TEST-ANALYST']={'dataset_id':'TEST-ANALYST','kind':'analyst_market_data','status':'available','version':'synthetic-tests-only','git_values_allowed':True,'market_definitions':{'TEST-CHINA-ETCH':{'native_category':'Synthetic China etch','category_id':'etch','population':'all_vendors','methodology':'Synthetic fixture; no empirical interpretation','category_mapping_rationale':'Exact synthetic fixture mapping','dimensions':copy.deepcopy(d['dimensions'])}}}
    data['sources']['TEST-SOURCE']={'source_id':'TEST-SOURCE','dataset_id':'TEST-ANALYST','sha256':'0'*64,'title':'SYNTHETIC TEST ONLY','publication_date':'2026-01-01','page_count':100,'locator_kind':'pdf'}
    bind_synthetic(n);bind_synthetic(d)
    data['observations'].update({'TEST-N':n,'TEST-D':d})
    recipe={'reconciliation_id':'TEST-R','kind':'market_share','question':'Synthetic fixture only','numerator_id':'TEST-N','denominator_id':'TEST-D','adjustments':[]}
    return data,n,d,recipe

class EvidenceTests(unittest.TestCase):
    def test_production_dataset_validates(self):
        r=validate(load());self.assertGreaterEqual(r['observations'],57)
        self.assertEqual(r['source_availability'],'not_checked')

    def test_revenue_cannot_be_chambers(self):
        data=load();o=copy.deepcopy(data['observations']['A2025-ER']);o['unit']='chamber'
        with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_native_wan_yuan_preserves_decimal_value(self):
        data,n,d,recipe=synthetic_market()
        n.update(value='86312.71',unit='CNY_10k');bind_synthetic(n)
        validate_observation(n,data)
        self.assertEqual(money(n),(Decimal('863127100'), 'CNY'))

    def test_wan_yuan_and_yi_yuan_reconcile_at_correct_scale(self):
        data,n,d,recipe=synthetic_market()
        n.update(value='12345.67',unit='CNY_10k')
        d.update(value='2.469134',unit='CNY_100m');bind_synthetic(n);bind_synthetic(d)
        validate_observation(n,data)
        validate_observation(d,data)
        self.assertEqual(reconcile(recipe,data)['value'],'50.0000')

    def test_negative_value_requires_metric_opt_in(self):
        data=load();o=copy.deepcopy(data['observations']['A2025-ER'])
        data['metrics']['operating_cash_flow']={
            'metric_id':'operating_cash_flow','time_bases':['flow'],'units':['CNY'],
            'definition':'Synthetic signed cash-flow metric for validator testing.','allow_negative':True}
        o.update(metric_id='operating_cash_flow',unit='CNY',value='-562876699.27');bind_synthetic(o)
        validate_observation(o,data)
        data['metrics']['operating_cash_flow'].pop('allow_negative')
        with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_negative_equipment_count_remains_rejected(self):
        data=load();o=copy.deepcopy(data['observations']['A2025-SS']);o['value']='-1'
        with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_signed_metric_still_rejects_nonnumeric_value(self):
        data=load();o=copy.deepcopy(data['observations']['A2025-ER'])
        data['metrics']['operating_cash_flow']={
            'metric_id':'operating_cash_flow','time_bases':['flow'],'units':['CNY'],
            'definition':'Synthetic signed cash-flow metric for validator testing.','allow_negative':True}
        o.update(metric_id='operating_cash_flow',unit='CNY',value='not-a-number')
        with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_signed_metric_still_rejects_nonfinite_value(self):
        data=load();o=copy.deepcopy(data['observations']['A2025-ER'])
        data['metrics']['operating_cash_flow']={
            'metric_id':'operating_cash_flow','time_bases':['flow'],'units':['CNY'],
            'definition':'Synthetic signed cash-flow metric for validator testing.','allow_negative':True}
        o.update(metric_id='operating_cash_flow',unit='CNY')
        for value in ('NaN','Infinity'):
            with self.subTest(value=value):
                o['value']=value
                with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_signed_metric_range_must_still_be_ordered(self):
        data=load();o=copy.deepcopy(data['observations']['A2025-ER'])
        data['metrics']['operating_cash_flow']={
            'metric_id':'operating_cash_flow','time_bases':['flow'],'units':['CNY'],
            'definition':'Synthetic signed cash-flow metric for validator testing.','allow_negative':True}
        o.update(metric_id='operating_cash_flow',unit='CNY',value='-10',relation='range',upper_value='-2');bind_synthetic(o)
        validate_observation(o,data)
        o['upper_value']='-11'
        with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_interim_revenue_is_supported(self):
        data=load();o=copy.deepcopy(data['observations']['A2025-ER']);o['period'].update(kind='interim',end='2025-06-30')
        validate_observation(o,data)

    def test_broad_2025_count_excluded(self):
        data=load();s=next(s for s in data['series'] if s['series_id']=='amec_etch_sales')
        self.assertNotIn('A2025-SS',s['observation_ids'])
        s['observation_ids'].append('A2025-SS')
        with self.assertRaises(ValidationError):validate(data)

    def test_approaching_is_not_point_value(self):
        self.assertEqual(load()['observations']['A2025H1-UD-INST']['relation'],'approaching')

    def test_revisions_retained(self):
        data=load();self.assertEqual(data['observations']['N2024-CR-R']['revision_of'],'N2024-CR')
        data['observations']['N2024-CR-R']['period']['end']='2025-12-31'
        with self.assertRaises(ValidationError):validate(data)

    def test_customers_and_lines_have_distinct_units(self):
        data=load();o=copy.deepcopy(data['observations']['A2024H1-ICP-LINES']);o['unit']='customer'
        with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_analyst_definition_required(self):
        data,n,d,r=synthetic_market();validate(data)
        d.pop('market_definition_id')
        with self.assertRaises(ValidationError):validate_observation(d,data)

    def test_analyst_cannot_be_relabelled_fact(self):
        data,n,d,r=synthetic_market();d['claim_kind']='company_reported'
        with self.assertRaises(ValidationError):validate_observation(d,data)

    def test_unapproved_licensed_values_rejected(self):
        data,n,d,r=synthetic_market();data['datasets']['TEST-ANALYST']['git_values_allowed']=False
        with self.assertRaises(ValidationError):validate_observation(d,data)

    def test_definition_mapping_must_match(self):
        data,n,d,r=synthetic_market();d['category_id']='etch_icp'
        with self.assertRaises(ValidationError):validate_observation(d,data)

    def test_stock_change_not_shipments(self):
        data=load();o=data['observations']['A2025H1-CCP-DELTA']
        self.assertEqual(o['period']['basis'],'stock_change')
        self.assertEqual(o['period']['start'],'2024-06-30')

    def test_scope_cannot_be_relabelled_category(self):
        data=load();o=data['observations']['A2025-ER'];o['reporting_scope_id']='naura_electronic_process_equipment'
        with self.assertRaises(ValidationError):validate_observation(o,data)

    def test_dimensions_cannot_be_null(self):
        data,n,d,r=synthetic_market();n['dimensions']['tax_basis']=None
        with self.assertRaises(ValidationError):validate_observation(n,data)

    def test_unknown_series_mode_rejected(self):
        data=load();data['series'][0]['mode']='comparabl'
        with self.assertRaises(ValidationError):validate(data)

class ReconciliationTests(unittest.TestCase):
    def test_real_market_share_is_blocked(self):
        data=load();r=reconcile(data['reconciliations'][1],data)
        self.assertEqual(r['status'],'blocked');self.assertIsNone(r['value'])

    def test_real_portfolio_mix_propagates_approximation(self):
        data=load();r=reconcile(data['reconciliations'][0],data)
        self.assertEqual(r['status'],'computed');self.assertEqual(r['relation'],'approx')
        self.assertTrue(r['approximate']);self.assertIsNone(r['lower_value'])

    def test_explicit_approximate_qualifiers_preserved(self):
        data=load()
        for oid in ['A2023-EO','A2023-ER','A2024-ER','A2025-ER']:
            self.assertEqual(data['observations'][oid]['relation'],'approx')
        self.assertEqual(data['observations']['A2022-ER']['relation'],'eq')

    def test_synthetic_matched_market_share(self):
        data,n,d,recipe=synthetic_market()
        self.assertEqual(reconcile(recipe,data)['value'],'50.0000')

    def test_geography_mismatch_blocked(self):
        data,n,d,recipe=synthetic_market();n['dimensions']['geography']='worldwide'
        self.assertEqual(reconcile(recipe,data)['status'],'blocked')

    def test_unknown_material_dimension_blocked(self):
        data,n,d,recipe=synthetic_market();n['dimensions']['tax_basis']=d['dimensions']['tax_basis']='unknown'
        self.assertEqual(reconcile(recipe,data)['status'],'blocked')

    def test_period_mismatch_blocked(self):
        data,n,d,recipe=synthetic_market();d['period']['end']='2025-06-30'
        self.assertEqual(reconcile(recipe,data)['status'],'blocked')

    def test_revenue_vs_purchases_blocked(self):
        data,n,d,recipe=synthetic_market();d['dimensions']['revenue_basis']='customer_purchases'
        self.assertEqual(reconcile(recipe,data)['status'],'blocked')

    def test_lower_bound_ratio_not_fabricated(self):
        data,n,d,recipe=synthetic_market();n['relation']='gt'
        r=reconcile(recipe,data);self.assertEqual(r['status'],'computed')
        self.assertIsNone(r['value']);self.assertEqual(r['relation'],'range');self.assertEqual(r['lower_value'],'50.0000');self.assertEqual(r['upper_value'],'100.0000')

    def test_explicit_allocation_labelled_scenario(self):
        data,n,d,recipe=synthetic_market();n['dimensions']['geography']='worldwide'
        recipe['adjustments']=[dict(assumption_id='TEST-ALLOCATION',side='numerator',operation='allocate',factor='0.5',dimension_changes={'geography':'China'},rationale='Synthetic sensitivity assumption',evidence_status='assumed')]
        result=reconcile(recipe,data)
        self.assertEqual(result['value'],'25.0000');self.assertEqual(result['result_kind'],'scenario_estimate')

    def test_fx_requires_explicit_conversion(self):
        data,n,d,recipe=synthetic_market();d['unit']='USD';d['value']='20'
        self.assertEqual(reconcile(recipe,data)['status'],'blocked')
        recipe['adjustments']=[dict(assumption_id='TEST-FX',side='denominator',operation='currency_convert',factor='10',to_currency='CNY',rationale='Synthetic rate, not actual exchange rate',evidence_status='assumed')]
        self.assertEqual(reconcile(recipe,data)['value'],'50.0000')

    def test_implied_market_size(self):
        data,n,d,recipe=synthetic_market();d.update(metric_id='reported_market_share',unit='percent',value='25',entity_id='amec');recipe['kind']='implied_market_size'
        result=reconcile(recipe,data)
        self.assertEqual(result['value'],'400.0000');self.assertEqual(result['unit'],'CNY');self.assertEqual(result['result_kind'],'implied_estimate')

    def test_cannot_convert_percent_as_currency(self):
        data,n,d,recipe=synthetic_market();d.update(metric_id='reported_market_share',unit='percent',value='25',entity_id='amec');recipe['kind']='implied_market_size'
        recipe['adjustments']=[dict(assumption_id='TEST-FX',side='denominator',operation='currency_convert',factor='10',to_currency='USD',rationale='Invalid synthetic conversion',evidence_status='assumed')]
        with self.assertRaises(ValidationError):reconcile(recipe,data)

    def test_implied_size_converts_only_revenue(self):
        data,n,d,recipe=synthetic_market();d.update(metric_id='reported_market_share',unit='percent',value='25',entity_id='amec');recipe['kind']='implied_market_size'
        recipe['adjustments']=[dict(assumption_id='TEST-FX',side='numerator',operation='currency_convert',factor='0.1',to_currency='USD',rationale='Synthetic conversion',evidence_status='assumed')]
        result=reconcile(recipe,data);self.assertEqual(result['value'],'40.0000');self.assertEqual(result['unit'],'USD')

    def test_over_100_share_rejected(self):
        data,n,d,recipe=synthetic_market();n['value']='250'
        self.assertEqual(reconcile(recipe,data)['status'],'blocked')

    def test_zero_denominator_blocked(self):
        data,n,d,recipe=synthetic_market();d['value']='0'
        self.assertEqual(reconcile(recipe,data)['status'],'blocked')

    def test_snapshot_cannot_recurse_into_build(self):
        with self.assertRaises(ValidationError):snapshot(ROOT,ROOT/'build/do-not-create')

if __name__=='__main__':unittest.main()


class CrossScopeCoincidenceTests(unittest.TestCase):
    """The duplicates report must surface one figure carried under two scopes of one filing.

    Its original grouping key included reporting_scope_id, so it reported zero unresolved groups
    while 251 undeclared cross-scope coincidences sat in the atlas, 68 of them spanning more than
    one category_id. Within a scope a duplicate is usually a harmless restatement; across scopes the
    rows are parallel partitions of one perimeter, and when their categories differ an equipment
    rollup and a company rollup can each count the same money.
    """

    def setUp(self):
        self.report = cli.duplicates()

    def test_cross_scope_class_is_reported(self):
        for k in ('cross_scope_groups', 'cross_scope_undeclared', 'cross_scope_spanning_categories'):
            self.assertIn(k, self.report)
        self.assertGreaterEqual(self.report['cross_scope_groups'], self.report['cross_scope_undeclared'])

    def test_cross_scope_groups_really_span_scopes(self):
        for g in self.report['cross_scope']:
            self.assertGreater(len(g['scopes']), 1, g['observation_ids'])
            self.assertGreater(len(g['observation_ids']), 1)
            self.assertEqual(g['spans_categories'], len(g['category_ids']) > 1)

    def test_category_spanning_groups_are_listed_first(self):
        shown = self.report['cross_scope']
        undeclared = [g for g in shown if g['status'] == 'undeclared']
        if undeclared:
            spanning = [i for i, g in enumerate(undeclared) if g['spans_categories']]
            plain = [i for i, g in enumerate(undeclared) if not g['spans_categories']]
            if spanning and plain:
                self.assertLess(max(spanning), min(plain))

    def test_declared_coincidence_drops_out_of_the_undeclared_list(self):
        """The verified Piotech FY2023 pair is declared, so it must not read as undeclared.

        Like the main report, cross_scope shows the undeclared groups when there are any and
        suppresses the resolved ones, so a declaration is confirmed by absence plus the counts.
        """
        undeclared = {i for g in self.report['cross_scope'] if g['status'] == 'undeclared'
                      for i in g['observation_ids']}
        self.assertNotIn('W13GEO-PIOTECH-CN-2023-REV', undeclared)
        self.assertNotIn('W13GEO-PIOTECH-CN-2023-COST', undeclared)
        self.assertGreater(self.report['cross_scope_groups'], self.report['cross_scope_undeclared'],
                           'at least one cross-scope group should be declared')


class PlatformAliasCoverageTests(unittest.TestCase):
    """verify_aliases must look at platform aliases, not only entity aliases.

    It was built after an invented Chinese name was found on an entity. A later wave found an
    invented model number on a PLATFORM — a class the tool had never examined, so the fix for the
    first fabrication did not cover the second. A model number is the likelier fabrication of the
    two: it looks right, and it is what a reader searching for a tool matches on.
    """

    def test_platform_aliases_are_in_scope_for_the_checker(self):
        """Assert the checker walks platforms, without running it.

        verify_aliases shells out to pdftotext twice for every source, so calling it from the suite
        would add hundreds of subprocess invocations and make the result depend on a gitignored,
        machine-specific source tree — which is exactly why the module's own docstring says it is a
        local-corpus check rather than a test. Reading the source for the traversal is enough to
        pin that platform aliases are covered at all, which is the regression that mattered.
        """
        body = (ROOT / 'atlas/aliases.py').read_text(encoding='utf-8')
        self.assertIn("data['platforms']", body)
        self.assertIn("'kind': 'platform'", body)
        self.assertIn("'kind': 'entity'", body)

    def test_every_platform_alias_names_a_source_the_atlas_holds(self):
        """An alias needs a held page. The fix for a gap is to acquire the page, not delete the name.

        This test replaces one that asserted no alias could contain "8210", written when SAB8210CWW was
        believed fabricated. It is a real model designation on the issuer's own product page; the atlas
        just did not hold that page. Hard-coding the absence of a real string would have made the
        earlier mistake permanent, so the invariant is the general one: every platform alias must have
        a source registered against its entity that a reader could go and check.
        """
        data = load()
        publisher = {}
        for sid, source in data['sources'].items():
            dataset = data['datasets'].get(source.get('dataset_id')) or {}
            publisher[sid] = dataset.get('publisher')
        for platform in data['platforms'].values():
            if not platform.get('aliases'):
                continue
            own = [s for s, pub in publisher.items() if pub == platform['entity_id']]
            self.assertTrue(own, f"{platform['platform_id']} carries aliases but its entity publishes no source")
