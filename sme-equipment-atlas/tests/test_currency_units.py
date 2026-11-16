"""Currencies are recorded as printed and never converted.

Foreign incumbents report in JPY, EUR, KRW and HKD. Admitting those units is only safe while two
things hold: the scale a unit declares in the schema is the scale the monetary map applies, and a
reconciliation whose sides differ in currency refuses to compute without an explicit FX adjustment.
Both are asserted here, because a silent exchange rate is the one way a comparator could corrupt a
domestic figure after `entity_class` has done its job.
"""
import json
import unittest
from decimal import Decimal
from pathlib import Path

from atlas.core import MONETARY, reconcile

ROOT = Path(__file__).resolve().parent.parent
UNITS = json.loads((ROOT / 'data/schema.json').read_text(encoding='utf-8'))['x-atlas-units']


class CurrencyUnitTests(unittest.TestCase):
    def test_every_monetary_unit_exists_in_the_schema_with_the_same_scale(self):
        for unit, scale in sorted(MONETARY.items()):
            with self.subTest(unit=unit):
                self.assertIn(unit, UNITS, f'{unit}: in MONETARY but not in x-atlas-units')
                self.assertEqual(Decimal(UNITS[unit]['scale']), scale,
                                 f'{unit}: schema scale and MONETARY scale disagree')

    def test_a_currency_unit_shares_a_base_unit_only_with_its_own_currency(self):
        """CNY_100m converts to CNY; it must never share a base unit with JPY_100m, or a scale
        change would silently become a currency conversion."""
        for unit in sorted(MONETARY):
            with self.subTest(unit=unit):
                self.assertEqual(UNITS[unit]['base_unit'], unit.split('_')[0])

    def test_the_declared_currencies_are_the_ones_we_expect(self):
        self.assertEqual(sorted({u.split('_')[0] for u in MONETARY}),
                         ['CNY', 'EUR', 'HKD', 'JPY', 'KRW', 'USD'])

    def test_a_cross_currency_reconciliation_is_blocked(self):
        data = {'observations': {
            'n': self._row('n', '100', 'JPY_million'),
            'd': self._row('d', '500', 'CNY_million')}, 'sources': {}, 'datasets': {}}
        result = reconcile({'reconciliation_id': 'x', 'question': 'q', 'kind': 'company_revenue_mix',
                            'numerator_id': 'n', 'denominator_id': 'd'}, data)
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(any('Currency differs' in r for r in result['reasons']),
                        f'expected a currency objection, got {result["reasons"]}')

    @staticmethod
    def _row(oid, value, unit):
        return {'observation_id': oid, 'value': value, 'unit': unit, 'relation': 'eq',
                'precision': 'reported', 'metric_id': 'revenue', 'entity_id': 'e',
                'source_id': 's', 'evidence': {'status': 'source_checked'},
                'period': {'start': '2025-01-01', 'end': '2025-12-31', 'kind': 'annual', 'basis': 'flow'},
                'category_id': 'all_businesses', 'reporting_scope_id': 'company', 'dimensions': {}}


if __name__ == '__main__':
    unittest.main()
