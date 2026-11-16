"""Adversarial checks for source-worded losses and shareholder identity boundaries."""
import copy
import unittest
from atlas.core import load, validate_observation, validate, ValidationError, observation_export, display_scope
from tests.evidence_fixtures import bind_synthetic

class SourceLossTests(unittest.TestCase):
    def setUp(self):
        self.data=load()
        self.data['metrics']['fair_value_change_income']['allow_source_loss']=True
        self.row=copy.deepcopy(self.data['observations']['A2025-CR'])
        self.row.update(metric_id='fair_value_change_income',value='-1.01',unit='CNY_100m',relation='eq')
        bind_synthetic(self.row)
        self.row['evidence'].update(reported_value='1.01',excerpt='本期公允价值变动损失 1.01 亿元',conversion={'operation':'multiply','factor':'-1','sign_basis':'source_reported_loss'})

    def test_loss_sign_and_scaled_arithmetic_preserve_native_magnitude(self):
        validate_observation(self.row,self.data)
        scaled=copy.deepcopy(self.row);scaled.update(unit='CNY',value='-101000000')
        scaled['evidence']['conversion']['factor']='-100000000'
        validate_observation(scaled,self.data)
        for field,value in [('value','101000000'),('value','-10100000')]:
            bad=copy.deepcopy(scaled);bad[field]=value
            with self.assertRaises(ValidationError):validate_observation(bad,self.data)
        bad=copy.deepcopy(scaled);bad['evidence']['conversion']['factor']='-1'
        with self.assertRaises(ValidationError):validate_observation(bad,self.data)

    def test_loss_requires_governing_source_words_and_matching_qualifier(self):
        for excerpt in ['利润 1.01 亿元，损失 2 亿元','非损失 1.01 亿元','不是损失 1.01 亿元','未亏损 1.01 亿元','下降 1.01 亿元','损失 -1.01 亿元','没有损失 1.01 亿元','未发生亏损 1.01 亿元','未产生损失 1.01 亿元','不发生亏损 1.01 亿元','无重大损失 1.01 亿元','不存在损失 1.01 亿元','未发生任何重大亏损 1.01 亿元']:
            bad=copy.deepcopy(self.row);bad['evidence']['excerpt']=excerpt
            with self.subTest(excerpt=excerpt),self.assertRaises(ValidationError):validate_observation(bad,self.data)
        valid=copy.deepcopy(self.row);valid['evidence']['excerpt']='无形资产减值损失 1.01 亿元'
        validate_observation(valid,self.data)
        negative=copy.deepcopy(self.row);negative['evidence'].update(reported_value='-1.01',excerpt='投资损失 -1.01 亿元')
        with self.assertRaises(ValidationError):validate_observation(negative,self.data)
        approx=copy.deepcopy(self.row);approx['evidence']['excerpt']='股权投资亏损约 1.01 亿元'
        with self.assertRaises(ValidationError):validate_observation(approx,self.data)
        approx['relation']='approx';validate_observation(approx,self.data)
        approx['evidence']['excerpt']='股权投资亏损 1.01 亿元'
        with self.assertRaises(ValidationError):validate_observation(approx,self.data)
        for relation in ['gt','ge','lt','le','approaching','range']:
            bad=copy.deepcopy(self.row);bad['relation']=relation
            with self.subTest(relation=relation),self.assertRaises(ValidationError):validate_observation(bad,self.data)

    def test_loss_needs_metric_opt_in_and_cannot_use_decrease_contract(self):
        for flag,value in [('allow_source_loss',False),('allow_negative',False)]:
            data=copy.deepcopy(self.data);data['metrics']['fair_value_change_income'][flag]=value
            with self.assertRaises(ValidationError):validate_observation(self.row,data)
            with self.assertRaises(ValidationError):validate(data)
        data=copy.deepcopy(self.data);data['metrics']['fair_value_change_income'].pop('allow_source_loss')
        with self.assertRaises(ValidationError):validate_observation(self.row,data)
        bad=copy.deepcopy(self.row);bad['evidence']['conversion']['sign_basis']='source_reported_decrease'
        self.data['metrics']['fair_value_change_income']['allow_source_decrease']=True
        with self.assertRaises(ValidationError):validate_observation(bad,self.data)

class ShareholderBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.data=load();self.row=copy.deepcopy(self.data['observations']['A2025-CR'])
        self.fields={'shareholder_table':'top_ten_shareholders','shareholder_rank':1,'reported_holder_name':'示例股东','holding_basis':'restricted_holding','share_class':'not_stated'}
        self.data['metrics']['test_holding']={'metric_id':'test_holding','units':['share'],'time_bases':['stock'],'dimension_schema':{'type':'object','required':list(self.fields)}}
        self.row.update(metric_id='test_holding',value='100',unit='share',period={'start':'','end':'2025-12-31','kind':'as_of','basis':'stock'})
        self.row['dimensions'].update(self.fields);bind_synthetic(self.row)

    def test_closed_holder_dimensions_require_complete_source_identity(self):
        validate_observation(self.row,self.data)
        for field in self.fields:
            bad=copy.deepcopy(self.row);bad['dimensions'].pop(field)
            with self.subTest(missing=field),self.assertRaises(ValidationError):validate_observation(bad,self.data)
        for field,value in [('shareholder_rank',0),('shareholder_rank',11),('shareholder_rank',True),('reported_holder_name',''),('holding_basis','beneficial_owner'),('share_class','inferred_class')]:
            bad=copy.deepcopy(self.row);bad['dimensions'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValidationError):validate_observation(bad,self.data)
        bad=copy.deepcopy(self.row);bad['dimensions']['reported_hodler_name']='Typo'
        with self.assertRaises(ValidationError):validate_observation(bad,self.data)

    def test_export_and_display_preserve_holder_table_and_column(self):
        exported=observation_export(self.row)
        for field,value in self.fields.items():self.assertEqual(exported[field],value)
        shown=display_scope(self.row)
        for value in self.fields.values():self.assertIn(str(value),shown)
        other=copy.deepcopy(self.row);other['dimensions']['holding_basis']='total_holding'
        self.assertNotEqual(display_scope(other),shown)

    def test_ordinary_shareholder_unit_is_not_person_or_share(self):
        row=copy.deepcopy(self.row);row['dimensions']={k:v for k,v in row['dimensions'].items() if k not in self.fields}
        row.update(metric_id='test_holder_count',unit='ordinary_shareholder')
        self.data['metrics']['test_holder_count']={'metric_id':'test_holder_count','units':['ordinary_shareholder','person','share'],'time_bases':['stock']}
        bind_synthetic(row);validate_observation(row,self.data)
        for unit in ['person','share']:
            bad=copy.deepcopy(row);bad['unit']=unit
            with self.subTest(unit=unit),self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(bad,self.data)
