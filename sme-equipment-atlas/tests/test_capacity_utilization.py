"""Capacity utilization is a nonnegative period ratio, not nameplate units."""
import copy
import unittest

from atlas.core import load, validate_observation, ValidationError
from tests.evidence_fixtures import bind_synthetic


class CapacityUtilizationTests(unittest.TestCase):
    def setUp(self):
        self.data = load()
        self.row = copy.deepcopy(self.data['observations']['A2025-CR'])
        self.row.update(metric_id='capacity_utilization', unit='percent',
                        value='87.30', relation='eq')
        self.row['period']['basis'] = 'period_status'
        bind_synthetic(self.row)

    def test_levels_allow_output_above_nominal_capacity(self):
        for value in ('0', '87.30', '100', '110.25'):
            with self.subTest(value=value):
                self.row['value'] = value
                bind_synthetic(self.row)
                validate_observation(self.row, self.data)

    def test_negative_utilization_is_not_a_change_measure(self):
        self.row['value'] = '-13.56'
        bind_synthetic(self.row)
        with self.assertRaises(ValidationError):
            validate_observation(self.row, self.data)

    def test_counts_and_stock_dates_cannot_replace_period_ratio(self):
        for field in ('unit', 'basis'):
            row = copy.deepcopy(self.row)
            if field == 'unit':
                row['unit'] = 'wafer_per_month'
                bind_synthetic(row)
            else:
                row['period']['basis'] = 'stock'
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_observation(row, self.data)
