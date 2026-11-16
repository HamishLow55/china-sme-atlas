"""Adversarial evidence-consistency regressions; no production edits."""
import copy
import unittest
from decimal import Decimal
from atlas.core import load, validate_observation, ValidationError
from atlas.evidence import numeric_tokens
from tests.evidence_fixtures import bind_synthetic

class NumericEvidenceTests(unittest.TestCase):
    def setUp(self):self.data=load()

    def test_digit_mutations_rejected_across_entire_ledger(self):
        for original in self.data['observations'].values():
            row=copy.deepcopy(original);row['value']=str(Decimal(row['value'])+Decimal('0.01'))
            with self.subTest(id=row['observation_id']),self.assertRaises(ValidationError):
                validate_observation(row,self.data)

    def test_metric_allowed_unit_swaps_rejected_without_series_dependency(self):
        checked=0
        for original in self.data['observations'].values():
            for unit in self.data['metrics'][original['metric_id']]['units']:
                if unit==original['unit']:continue
                row=copy.deepcopy(original);row['unit']=unit;checked+=1
                with self.subTest(id=row['observation_id'],unit=unit),self.assertRaises(ValidationError):
                    validate_observation(row,self.data)
        self.assertGreater(checked,100)

    def test_page_bound_and_unrelated_excerpt(self):
        original=self.data['observations']['AMEC2022-COMPANY-COST']
        for field,value in [('page',99999),('excerpt','Unrelated prose without quantitative evidence.')]:
            row=copy.deepcopy(original);row['evidence'][field]=value
            with self.subTest(field=field),self.assertRaises(ValidationError):validate_observation(row,self.data)

    def test_sign_decimal_and_token_boundaries(self):
        tokens=numeric_tokens('Loss −1,234.50; standalone 3123; 0.125; 超百亿元')
        self.assertIn(Decimal('-1234.50'),tokens)
        self.assertNotIn(Decimal('1234.50'),tokens)
        self.assertNotIn(Decimal('123'),tokens)
        self.assertIn(Decimal('0.125'),tokens)
        self.assertIn(Decimal(100),tokens)

    def test_lexical_hundred_requires_explicit_bound(self):
        original=self.data['observations']['N2025-ER']
        for excerpt in ['该项目预算数百亿元人民币。','未超过百亿元','百亿元','几百亿元']:
            row=copy.deepcopy(original);row['evidence']['excerpt']=excerpt
            with self.subTest(excerpt=excerpt),self.assertRaises(ValidationError):validate_observation(row,self.data)
        row=copy.deepcopy(original);row['relation']='eq'
        with self.assertRaises(ValidationError):validate_observation(row,self.data)

    def test_accounting_parentheses_preserve_negative_sign(self):
        for excerpt in ['Loss (12,315.42)', '亏损（12，315.42）', 'Loss ( 12,315.42 )']:
            with self.subTest(excerpt=excerpt):
                self.assertEqual(numeric_tokens(excerpt),{Decimal('-12315.42')})
        row=copy.deepcopy(self.data['observations']['A2025-CR'])
        row.update(metric_id='net_profit',value='-12315.42',unit='CNY')
        bind_synthetic(row)
        row['evidence']['excerpt']='净利润 (12,315.42) 元'
        validate_observation(row,self.data)
        row['value']='12315.42';row['evidence']['reported_value']='12315.42'
        with self.assertRaises(ValidationError):validate_observation(row,self.data)

    def test_per_share_unit_cannot_be_relabelled_as_currency_amount(self):
        self.data['metrics']['test_eps']={'metric_id':'test_eps','units':['CNY_per_share','CNY'], 'time_bases':['flow'],'allow_negative':True}
        row=copy.deepcopy(self.data['observations']['A2025-CR'])
        row.update(metric_id='test_eps',value='1.23',unit='CNY_per_share');bind_synthetic(row)
        validate_observation(row,self.data)
        row['unit']='CNY'
        with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(row,self.data)

    def test_share_and_process_counts_preserve_distinct_dimensions(self):
        for unit in ['share', 'process']:
            self.data['metrics']['test_native_count'] = {
                'metric_id': 'test_native_count',
                'units': [unit, 'system', 'chamber'], 'time_bases': ['flow']}
            row = copy.deepcopy(self.data['observations']['A2025-CR'])
            row.update(metric_id='test_native_count', value='100', unit=unit)
            bind_synthetic(row)
            validate_observation(row, self.data)
            for wrong_unit in ['system', 'chamber']:
                changed = copy.deepcopy(row)
                changed['unit'] = wrong_unit
                with self.subTest(native=unit, stored=wrong_unit), self.assertRaisesRegex(
                        ValidationError, 'unit dimensions differ'):
                    validate_observation(changed, self.data)

    def test_probe_pin_monthly_capacity_preserves_scale_and_dimension(self):
        self.data['metrics']['test_pin_capacity'] = {
            'metric_id': 'test_pin_capacity', 'time_bases': ['flow'],
            'units': ['probe_pin_per_month', 'probe_pin_10k_per_month', 'probe_card', 'system']}
        row = copy.deepcopy(self.data['observations']['A2025-CR'])
        row.update(metric_id='test_pin_capacity', value='300', unit='probe_pin_10k_per_month')
        bind_synthetic(row)
        row['unit'] = 'probe_pin_per_month'
        row['value'] = '3000000'
        row['evidence']['conversion'] = {'operation': 'multiply', 'factor': '10000'}
        validate_observation(row, self.data)
        for unit, factor in [('probe_pin_per_month', '1000'), ('probe_card', '10000'), ('system', '10000')]:
            changed = copy.deepcopy(row)
            changed['unit'] = unit
            changed['evidence']['conversion']['factor'] = factor
            with self.subTest(unit=unit, factor=factor), self.assertRaises(ValidationError):
                validate_observation(changed, self.data)

    def test_probe_cards_cannot_be_converted_to_systems(self):
        row = copy.deepcopy(self.data['observations']['A2025-CR'])
        row.update(metric_id='production_volume', value='12', unit='probe_card')
        bind_synthetic(row)
        validate_observation(row, self.data)
        for wrong_unit in ['system', 'chamber']:
            changed = copy.deepcopy(row)
            changed['unit'] = wrong_unit
            changed['evidence']['conversion'] = {'operation': 'multiply', 'factor': '1'}
            with self.subTest(unit=wrong_unit), self.assertRaisesRegex(
                    ValidationError, 'unit dimensions differ'):
                validate_observation(changed, self.data)

    def test_ip_items_cannot_be_converted_to_people_or_equipment(self):
        self.data['metrics']['test_ip_items'] = {
            'metric_id': 'test_ip_items',
            'units': ['intellectual_property_item', 'person', 'system', 'chamber'],
            'time_bases': ['flow']}
        row = copy.deepcopy(self.data['observations']['A2025-CR'])
        row.update(metric_id='test_ip_items', value='28', unit='intellectual_property_item')
        bind_synthetic(row)
        validate_observation(row, self.data)
        for wrong_unit in ['person', 'system', 'chamber']:
            changed = copy.deepcopy(row)
            changed['evidence']['reported_unit'] = wrong_unit
            changed['evidence']['conversion'] = {'operation': 'multiply', 'factor': '1'}
            with self.subTest(native=wrong_unit), self.assertRaisesRegex(
                    ValidationError, 'unit dimensions differ'):
                validate_observation(changed, self.data)

    def test_exact_source_conversion_is_required_and_checked(self):
        original=next(o for o in self.data['observations'].values()
                      if o['unit']=='USD_million'
                      and o['evidence']['reported_unit']=='USD_thousand'
                      and 'conversion' in o['evidence'])
        validate_observation(original,self.data)
        for patch in ['omit','wrong_factor','wrong_native_unit','wrong_native_value']:
            row=copy.deepcopy(original);e=row['evidence']
            if patch=='omit':e.pop('conversion')
            if patch=='wrong_factor':e['conversion']['factor']='1000'
            if patch=='wrong_native_unit':e['reported_unit']='CNY_10k'
            if patch=='wrong_native_value':e['reported_value']='1'
            with self.subTest(patch=patch),self.assertRaises(ValidationError):validate_observation(row,self.data)

    def test_range_binds_both_endpoints(self):
        row=copy.deepcopy(self.data['observations']['AMEC2022-COMPANY-COST'])
        row.update(value='10',upper_value='20',relation='range');bind_synthetic(row)
        validate_observation(row,self.data)
        row['upper_value']='21'
        with self.assertRaises(ValidationError):validate_observation(row,self.data)
