"""Source-native counts must remain tied to their MEMS wafer-line size."""
import copy
import unittest
from atlas.core import load, validate_observation, ValidationError
from tests.evidence_fixtures import bind_synthetic


class LexicalMemsLinesTests(unittest.TestCase):
    def setUp(self):
        self.data = load()
        self.data['metrics']['internal_mems_production_line_count'] = {
            'metric_id': 'internal_mems_production_line_count',
            'units': ['production_line', 'system'], 'time_bases': ['period_status']}
        self.row = copy.deepcopy(self.data['observations']['A2025-CR'])
        self.row.update(metric_id='internal_mems_production_line_count', value='3',
                        unit='production_line', relation='eq')
        self.row['period']['basis'] = 'period_status'
        self.row['dimensions']['wafer_line_size'] = '8_inch'
        bind_synthetic(self.row)
        self.row['evidence']['excerpt'] = '目前已拥有三条 8 寸 MEMS 产线和一条 12 寸 MEMS 产线'

    def test_counts_bind_to_size_without_rewriting_source(self):
        validate_observation(self.row, self.data)
        row = copy.deepcopy(self.row)
        row['value'] = row['evidence']['reported_value'] = '1'
        row['dimensions']['wafer_line_size'] = '12_inch'
        validate_observation(row, self.data)
        for size in ['8_inch', '12_inch']:
            bad = copy.deepcopy(row if size=='8_inch' else self.row)
            bad['dimensions']['wafer_line_size'] = size
            with self.subTest(size=size), self.assertRaises(ValidationError):
                validate_observation(bad, self.data)

    def test_rejects_partial_numbers_negation_and_wrong_nouns(self):
        for text in ['目前已拥有十三条8寸MEMS产线', '目前已拥有三十条8寸MEMS产线',
                     '没有目前已拥有三条8寸MEMS产线', '目前未拥有三条8寸MEMS产线',
                     '目前已拥有非三条8寸MEMS产线', '目前已拥有三条8寸MEMS设备',
                     '三条', '目前已拥有三条8寸MEMS产线和一条12寸MEMS产线并非事实']:
            row = copy.deepcopy(self.row)
            row['evidence']['excerpt'] = text
            with self.subTest(text=text), self.assertRaises(ValidationError):
                validate_observation(row, self.data)

    def test_wrong_metric_unit_relation_and_period_cannot_use_lexical_path(self):
        for patch in ['metric', 'unit', 'relation', 'period']:
            row = copy.deepcopy(self.row)
            if patch=='metric':
                self.data['metrics']['other_line_count'] = dict(self.data['metrics']['internal_mems_production_line_count'], metric_id='other_line_count')
                row['metric_id'] = 'other_line_count'
            elif patch=='unit': row['unit'] = row['evidence']['reported_unit'] = 'system'
            elif patch=='relation': row['relation'] = 'gt'
            else: row['period']['basis'] = 'flow'
            with self.subTest(patch=patch), self.assertRaises(ValidationError):
                validate_observation(row, self.data)
