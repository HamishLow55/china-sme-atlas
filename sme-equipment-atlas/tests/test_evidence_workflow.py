import copy
import json
import tempfile
import unittest
from pathlib import Path
from atlas.core import load, validate_observation, ValidationError
from atlas.reviews import validate_reviews
from atlas.metric_review import validate_metric_proposal
from tests.evidence_fixtures import bind_synthetic


class EvidenceWorkflowTests(unittest.TestCase):
    def test_acmr_key_financials_preserve_native_currency_scale_and_cash_sign(self):
        data = load()
        for metric in ['rd_expense', 'operating_cash_flow', 'net_profit_attributable']:
            row = copy.deepcopy(data['observations']['acmr_fy2025_' + metric])
            validate_observation(row, data)
            self.assertEqual(row['unit'], 'USD_thousand')
            bad = copy.deepcopy(row)
            bad['unit'] = 'CNY'
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
            bad = copy.deepcopy(row)
            bad['value'] = str(float(row['value']) / 1000)
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        self.assertEqual(data['observations']['acmr_fy2025_operating_cash_flow']['value'], '-10325')

    def test_planned_equipment_capacity_preserves_rate_target_and_node_scope(self):
        data = load()
        row = copy.deepcopy(data['observations']['jingyi_jingwei_planned_capacity_advanced_12inch'])
        validate_observation(row, data)
        self.assertEqual(row['precision'], 'reported_plan')
        self.assertEqual(row['period'], {'start': '2026-01-01', 'end': '2026-12-31', 'kind': 'annual', 'basis': 'period_status'})
        for metric, unit, basis in [('production_capacity', 'system_per_year', 'stock'),
                                    ('planned_production_capacity', 'system', 'period_status'),
                                    ('planned_production_capacity', 'system_per_year', 'flow')]:
            bad = copy.deepcopy(row)
            bad.update(metric_id=metric, unit=unit)
            bad['period']['basis'] = basis
            bind_synthetic(bad)
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        bad = copy.deepcopy(row)
        bad['dimensions']['process_node'] = '28nm及以上'
        with self.assertRaises(ValidationError):
            validate_observation(bad, data)

    def test_elapsed_validation_snapshot_is_not_completed_cycle_or_mean(self):
        data = load()
        row = copy.deepcopy(data['observations']['jingyi_jingwei_november_validation_scs003_duration'])
        validate_observation(row, data)
        for metric, basis in [('reported_equipment_acceptance_duration', 'as_of'),
                              ('reported_equipment_validation_elapsed_duration', 'period_status')]:
            bad = copy.deepcopy(row)
            bad['metric_id'] = metric
            bad['period']['basis'] = basis
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        row['dimensions']['statistic'] = 'mean'
        with self.assertRaises(ValidationError):
            validate_observation(row, data)

    def test_acceptance_duration_requires_statistic_and_native_month_unit(self):
        data = load()
        row = copy.deepcopy(data['observations']['jingyi_jingwei_acceptance_duration_first_tools'])
        validate_observation(row, data)
        bad = copy.deepcopy(row)
        del bad['dimensions']['statistic']
        with self.assertRaises(ValidationError):
            validate_observation(bad, data)
        for unit in ['year', 'percent', 'system']:
            bad = copy.deepcopy(row)
            bad['unit'] = unit
            bind_synthetic(bad)
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        row['value'] = '-1'
        bind_synthetic(row)
        with self.assertRaises(ValidationError):
            validate_observation(row, data)

    def test_stock_share_requires_registered_denominator_and_bounded_percent(self):
        data = load()
        row = copy.deepcopy(data['observations']['jingyi_operational_sweep_114'])
        validate_observation(row, data)
        bad = copy.deepcopy(row)
        del bad['dimensions']['denominator_scope_id']
        with self.assertRaises(ValidationError):
            validate_observation(bad, data)
        bad = copy.deepcopy(row)
        bad['dimensions']['denominator_scope_id'] = 'nonexistent_scope'
        with self.assertRaisesRegex(ValidationError, 'unknown denominator'):
            validate_observation(bad, data)
        for value in ['-1', '100.01']:
            bad = copy.deepcopy(row)
            bad['value'] = value
            bind_synthetic(bad)
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        row['period']['basis'] = 'flow'
        with self.assertRaises(ValidationError):
            validate_observation(row, data)

    def test_adjusted_liabilities_remain_monetary_stock(self):
        data = load()
        row = copy.deepcopy(data['observations']['jingyi_operational_sweep_053'])
        validate_observation(row, data)
        self.assertNotEqual(row['reporting_scope_id'], 'company')
        for unit, basis in [('system', 'stock'), ('CNY_10k', 'flow')]:
            bad = copy.deepcopy(row)
            bad['unit'] = unit
            bad['period']['basis'] = basis
            bind_synthetic(bad)
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)

    def test_equipment_stock_change_requires_explicit_stock_and_comparison_basis(self):
        data = load()
        row = copy.deepcopy(data['observations']['jingyi_operational_sweep_004'])
        self.assertLess(float(row['value']), 0)
        for stock in ['order_backlog', 'purchase_intentions']:
            row['dimensions']['underlying_metric'] = stock
            validate_observation(row, data)
        bad = copy.deepcopy(row)
        del bad['dimensions']['underlying_metric']
        with self.assertRaises(ValidationError):
            validate_observation(bad, data)
        for basis in ['flow', 'stock']:
            bad = copy.deepcopy(row)
            bad['period']['basis'] = basis
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        bad = copy.deepcopy(row)
        bad['dimensions']['underlying_metric'] = 'new_orders'
        with self.assertRaises(ValidationError):
            validate_observation(bad, data)

    def test_purchase_intentions_are_nonnegative_stocks_in_count_or_money_units(self):
        data = load()
        row = copy.deepcopy(next(x for x in data['observations'].values()
                                 if x['metric_id'] == 'order_backlog' and x['unit'] == 'system'))
        row['metric_id'] = 'purchase_intentions'
        row['value'] = '21'
        row['relation'] = 'eq'
        for unit in ['system', 'CNY_10k', 'CNY_100m']:
            row['unit'] = unit
            bind_synthetic(row)
            validate_observation(row, data)
        for field, value in [('value', '-1'), ('unit', 'percent')]:
            bad = copy.deepcopy(row)
            bad[field] = value
            bind_synthetic(bad)
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        row['period']['start'] = '2020-01-01'
        row['period']['basis'] = 'flow'
        with self.assertRaises(ValidationError):
            validate_observation(row, data)

    def test_review_cap_and_closed_shape(self):
        data = load()
        oid = next(iter(data['observations']))
        row = dict(reviewer='Codex independent verifier', date='2026-09-23',
                   source_ids=[data['observations'][oid]['source_id']], observation_ids=[oid],
                   decisions={oid: 'accepted'}, holds=[], limitations=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root/'docs/reviews'; folder.mkdir(parents=True)
            path = folder/'test_sweep.json'
            path.write_text(json.dumps(row)); validate_reviews(data, root)
            for bad in [dict(row, values=[]), dict(row, limitations=['x'*50_001]), dict(row, decisions={})]:
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValidationError): validate_reviews(data, root)

    def test_new_metric_requires_explicit_reuse_decision(self):
        metrics = load()['metrics']
        new = dict(metric_id='synthetic_new', definition='Synthetic distinct meaning for test only')
        with self.assertRaises(ValidationError): validate_metric_proposal(new, metrics, None)
        decision = dict(compared_metric_ids=['new_orders'], reason='Synthetic distinct concept', semantic_validation='schema_only')
        validate_metric_proposal(new, metrics, decision)
        new['definition'] = metrics['new_orders']['definition']
        with self.assertRaises(ValidationError): validate_metric_proposal(new, metrics, decision)

    def test_acceptance_dispatch_ratio_allows_above_hundred_but_share_does_not(self):
        data = load()
        ratio = copy.deepcopy(data['observations']['djel_operational_sweep_041'])
        self.assertGreater(float(ratio['value']), 100)
        validate_observation(ratio, data)
        ratio['metric_id'] = 'revenue_share'
        with self.assertRaises(ValidationError): validate_observation(ratio, data)

    def test_reported_price_keeps_per_system_unit(self):
        data = load(); row = copy.deepcopy(data['observations']['yitang_held_numeric_041'])
        validate_observation(row, data)
        row['unit'] = 'CNY_10k'; bind_synthetic(row)
        with self.assertRaises(ValidationError): validate_observation(row, data)

    def test_selected_orders_preserve_lower_bound_and_flow(self):
        data = load(); row = copy.deepcopy(data['observations']['yitang_held_numeric_203'])
        self.assertEqual(row['relation'], 'gt'); validate_observation(row, data)
        row['period']['basis'] = 'stock'
        with self.assertRaises(ValidationError): validate_observation(row, data)

    def test_new_orders_accept_system_counts_but_not_stock_or_chambers(self):
        data = load()
        row = copy.deepcopy(next(x for x in data['observations'].values()
                                 if x['metric_id'] == 'new_orders'))
        row['unit'] = 'system'
        row['value'] = '9'
        row['relation'] = 'eq'
        bind_synthetic(row)
        validate_observation(row, data)
        for unit, basis in [('system', 'stock'), ('chamber', 'flow')]:
            bad = copy.deepcopy(row)
            bad['unit'] = unit
            bad['period']['basis'] = basis
            bind_synthetic(bad)
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)

    def test_monetary_shipments_are_flows_with_native_currency_binding(self):
        data = load()
        row = copy.deepcopy(data['observations']['acmr_fy2025_shipments_first'])
        validate_observation(row, data)
        for unit in ['system', 'USD_thousand']:
            bad = copy.deepcopy(row)
            bad['unit'] = unit
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        for basis in ['stock', 'cumulative']:
            bad = copy.deepcopy(row)
            bad['period']['basis'] = basis
            with self.assertRaises(ValidationError):
                validate_observation(bad, data)
        # Count-based shipments remain valid after monetary-unit extension.
        counted = next(x for x in data['observations'].values()
                       if x['metric_id'] == 'shipments' and x['unit'] == 'system')
        validate_observation(counted, data)
