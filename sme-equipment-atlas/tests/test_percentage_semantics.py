"""Keep rate changes, shares, percentage points and per-person amounts distinct."""
import copy
import unittest
from atlas.core import load,validate_observation,validate,ValidationError,display_scope,observation_export
from tests.evidence_fixtures import bind_synthetic

class PercentageSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.data=load();self.row=copy.deepcopy(self.data['observations']['A2025-CR'])
        self.data['metrics']['test_growth']={'metric_id':'test_growth','units':['percent'],'time_bases':['period_status'],'allow_negative':True,'percent_semantics':'relative_change'}
        self.row.update(metric_id='test_growth',unit='percent',value='150')
        self.row['period']['basis']='period_status';bind_synthetic(self.row)
    def test_signed_growth_can_exceed_one_hundred_but_shares_cannot(self):
        for value in ['150','-4.5']:
            self.row['value']=value;bind_synthetic(self.row);validate_observation(self.row,self.data)
        self.row.update(metric_id='gross_margin',value='150');self.row['period']['basis']='period_status';bind_synthetic(self.row)
        with self.assertRaisesRegex(ValidationError,'share exceeds'):validate_observation(self.row,self.data)
    def test_percent_opt_in_is_closed_and_unit_specific_even_if_unused(self):
        for change in [{'percent_semantics':'relative_changes'},{'units':['CNY']},{'units':['percent','CNY']}]:
            data=copy.deepcopy(self.data);data['metrics']['test_growth'].update(change)
            with self.assertRaises(ValidationError):validate(data)
    def test_percentage_points_cannot_be_relabelled_relative_percent(self):
        self.row['evidence']['reported_unit']='percentage_point'
        with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(self.row,self.data)
    def test_average_pay_cannot_be_relabelled_total_money(self):
        self.data['metrics']['test_pay']={'metric_id':'test_pay','units':['CNY_10k_per_person','CNY_10k'],'time_bases':['flow']}
        self.row.update(metric_id='test_pay',unit='CNY_10k_per_person',value='62.04');self.row['period']['basis']='flow';bind_synthetic(self.row)
        validate_observation(self.row,self.data)
        self.row['unit']='CNY_10k'
        with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(self.row,self.data)
    def test_new_dimensions_reject_unregistered_components_and_channels(self):
        for field,value in [('cost_component','foreign_content'),('sales_channel','invented')]:
            row=copy.deepcopy(self.row);row['dimensions'][field]=value
            with self.assertRaises(ValidationError):validate_observation(row,self.data)
    def test_render_compensation_group_without_headcount_cohorts(self):
        self.row['dimensions']['workforce_group']='rd_employees'
        self.assertIn('rd_employees',display_scope(self.row))
        self.row['dimensions'].update(cost_component='direct_materials',sales_channel='direct')
        exported=observation_export(self.row)
        self.assertEqual(exported['cost_component'],'direct_materials')
        self.assertEqual(exported['sales_channel'],'direct')
    def test_return_ratio_is_not_a_bounded_share(self):
        self.data['metrics']['test_growth']['percent_semantics']='unbounded_ratio'
        validate_observation(self.row,self.data)

    def test_attributable_profit_growth_preserves_source_worded_decline(self):
        self.row.update(metric_id='net_profit_attributable_year_on_year_growth',value='-31.40')
        bind_synthetic(self.row)
        self.row['evidence'].update(reported_value='31.40',excerpt='归母净利润较上年同期减少31.40%',conversion={'operation':'multiply','factor':'-1','sign_basis':'source_reported_decrease'})
        validate_observation(self.row,self.data)
        for defect in ['missing_conversion','positive_value','growth_wording']:
            row=copy.deepcopy(self.row)
            if defect=='missing_conversion':row['evidence'].pop('conversion')
            elif defect=='positive_value':row['value']='31.40'
            else:row['evidence']['excerpt']='归母净利润较上年同期增长31.40%'
            with self.subTest(defect=defect),self.assertRaises(ValidationError):validate_observation(row,self.data)

    def test_source_worded_decrease_has_auditable_sign_conversion(self):
        self.data['metrics']['test_change']={'metric_id':'test_change','units':['percentage_point'],'time_bases':['period_status'],'allow_negative':True,'allow_source_decrease':True}
        self.row.update(metric_id='test_change',value='-1.02',unit='percentage_point');bind_synthetic(self.row)
        self.row['evidence'].update(reported_value='1.02',excerpt='加权平均净资产收益率：减少1.02个百分点',conversion={'operation':'multiply','factor':'-1','sign_basis':'source_reported_decrease'})
        validate_observation(self.row,self.data)
        for excerpt in ['增加1.02个百分点','减少11.02个百分点；另列1.02','减少约1.02个百分点']:
            row=copy.deepcopy(self.row);row['evidence']['excerpt']=excerpt
            with self.subTest(excerpt=excerpt),self.assertRaises(ValidationError):validate_observation(row,self.data)
        row=copy.deepcopy(self.row);row['evidence']['excerpt']='减少约1.02个百分点';row['relation']='approx'
        validate_observation(row,self.data)
        for relation in ['gt','ge','lt','le','approaching','approx']:
            row=copy.deepcopy(self.row);row['relation']=relation
            with self.subTest(relation=relation),self.assertRaises(ValidationError):validate_observation(row,self.data)
        self.data['metrics']['test_change'].pop('allow_source_decrease')
        with self.assertRaises(ValidationError):validate_observation(self.row,self.data)
