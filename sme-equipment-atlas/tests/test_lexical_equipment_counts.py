import copy
import unittest
from decimal import Decimal
from atlas.evidence import lexical_equipment_counts, numeric_tokens
from atlas.core import load, validate_observation, ValidationError

class LexicalEquipmentCountsTests(unittest.TestCase):
    def row(self, excerpt='外延设备累计出货近千腔。'):
        data = load()
        row = copy.deepcopy(data['observations']['naura_fy2022_icp_shipments'])
        row.update(value='1000', relation='approaching')
        row['evidence'].update(excerpt=excerpt, reported_value='1000')
        return row, data

    def test_approaching_is_not_exact_or_installed(self):
        row, data = self.row()
        validate_observation(row, data)
        for relation in ['eq', 'gt', 'approx', 'lt']:
            bad = copy.deepcopy(row); bad['relation'] = relation
            with self.assertRaises(ValidationError): validate_observation(bad, data)
        row['metric_id'] = 'cumulative_installations'
        with self.assertRaises(ValidationError): validate_observation(row, data)

    def test_delivery_is_not_shipment_and_preserves_system_unit(self):
        row, data = self.row('设备累计交付量均突破千台。')
        row.update(metric_id='cumulative_equipment_deliveries', relation='gt', unit='system')
        row['evidence']['reported_unit'] = 'system'
        validate_observation(row, data)
        for metric in ['cumulative_shipments', 'cumulative_installations']:
            bad=copy.deepcopy(row); bad['metric_id']=metric
            with self.assertRaises(ValidationError): validate_observation(bad, data)
        row.update(unit='chamber'); row['evidence']['reported_unit']='chamber'
        with self.assertRaises(ValidationError): validate_observation(row, data)

    def test_qualitative_negated_conditional_and_changed_values_rejected(self):
        for text in ['累计交付数千台', '千台级设备稳定运行', '累计出货近千腔以上',
                     '累计交付量未突破千台', '预计累计出货近千腔',
                     '没有实现累计交付量突破千台', '目标累计交付量突破千台']:
            self.assertEqual(lexical_equipment_counts(text), [], text)
            self.assertNotIn(Decimal(1000), numeric_tokens(text), text)
        row, data=self.row(); row['value']='1001'; row['evidence']['reported_value']='1001'
        with self.assertRaises(ValidationError): validate_observation(row,data)

    def test_whitespace_does_not_change_binding(self):
        self.assertEqual(lexical_equipment_counts('外延设备累计出货近\n千腔，覆盖客户'),
                         [(Decimal(1000), 'chamber', 'approaching', 'cumulative_shipments')])
