import copy
import unittest
from atlas.core import load, validate, validate_observation, ValidationError, reconcile, observation_export
from tests.evidence_fixtures import bind_synthetic
from tests.test_atlas import synthetic_market

class DisclosureMetricTests(unittest.TestCase):
    def setUp(self):
        self.data=load();self.row=copy.deepcopy(self.data['observations']['A2025-CR'])
        self.row.update(metric_id='customer_sales_share',unit='percent',value='39.03')
        self.row['dimensions']['counterparty_bucket']='top_five';bind_synthetic(self.row)
    def test_counterparty_bucket_required_and_enum_closed(self):
        validate_observation(self.row,self.data)
        for value in [None,'foreign_content']:
            row=copy.deepcopy(self.row)
            if value is None:row['dimensions'].pop('counterparty_bucket')
            else:row['dimensions']['counterparty_bucket']=value
            with self.assertRaises(ValidationError):validate_observation(row,self.data)
    def test_workforce_requires_population_and_cohort(self):
        row=self.row;row.update(metric_id='employee_headcount',unit='person',value='100');row['period'].update(basis='period_status')
        row['dimensions'].pop('counterparty_bucket');row['dimensions'].update(workforce_group='rd_employees',workforce_breakdown='education',workforce_cohort='本科');bind_synthetic(row)
        validate_observation(row,self.data)
        for key in ['workforce_group','workforce_breakdown','workforce_cohort']:
            bad=copy.deepcopy(row);bad['dimensions'].pop(key)
            with self.subTest(key=key),self.assertRaises(ValidationError):validate_observation(bad,self.data)
        row['unit']='customer'
        with self.assertRaises(ValidationError):validate_observation(row,self.data)
    def test_balance_stock_not_flow(self):
        row=self.row;row.update(metric_id='inventory_carrying_amount',unit='CNY',value='100');row['dimensions'].pop('counterparty_bucket');bind_synthetic(row)
        with self.assertRaises(ValidationError):validate_observation(row,self.data)
        row['period'].update(start='',kind='as_of',basis='stock');validate_observation(row,self.data)
        row['metric_id']='cash_capital_expenditure'
        with self.assertRaises(ValidationError):validate_observation(row,self.data)
    def test_comparable_series_cannot_mix_customer_ranks(self):
        a=self.row;b=copy.deepcopy(a);b['observation_id']='TEST-RANK';b['dimensions']['counterparty_bucket']='rank_1'
        self.data['observations'].update({a['observation_id']:a,b['observation_id']:b})
        self.data['series']=[{'series_id':'TEST','mode':'comparable','observation_ids':[a['observation_id'],b['observation_id']]}]
        with self.assertRaisesRegex(ValidationError,'incompatible observations'):validate(self.data)
    def test_optional_reporting_dimensions_must_match_in_ratios(self):
        data,n,d,recipe=synthetic_market();n['dimensions']['consolidation_basis']='synthetic_different_perimeter'
        r=reconcile(recipe,data);self.assertEqual(r['status'],'blocked');self.assertTrue(any('consolidation_basis' in reason for reason in r['reasons']))
    def test_export_retains_rank_and_original_label(self):
        out=observation_export(self.row);self.assertEqual(out['counterparty_bucket'],'top_five')
        self.assertEqual(out['original_label'],self.row['evidence']['original_label'])
