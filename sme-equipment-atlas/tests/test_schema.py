"""Integrity regressions for the declared observation contract."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from atlas.core import ROOT, ValidationError, load, validate_observation

class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.data=load()
        self.row=copy.deepcopy(self.data['observations']['AMEC2022-COMPANY-COST'])

    def test_closed_observation_and_nested_fields(self):
        for path in [(),('dimensions',),('evidence',),('period',)]:
            with self.subTest(path=path):
                row=copy.deepcopy(self.row);target=row
                for key in path:target=target[key]
                target['invented_field']='not part of the contract'
                with self.assertRaisesRegex(ValidationError,'unknown fields'):validate_observation(row,self.data)

    def test_wrong_types_and_unregistered_reviewer(self):
        for key,value in [('page',True),('page','63'),('reviewer','me'),('independent_corroboration','false')]:
            with self.subTest(key=key,value=value):
                row=copy.deepcopy(self.row);row['evidence'][key]=value
                with self.assertRaises(ValidationError):validate_observation(row,self.data)

    def test_future_review_date_rejected(self):
        self.row['evidence']['review_date']='2099-01-01'
        with self.assertRaisesRegex(ValidationError,'future review date'):validate_observation(self.row,self.data)

    def test_qualifier_review_uses_registered_identity_and_current_date(self):
        original=self.data['observations']['A2025-ER']
        for field,value in [('reviewer','me'),('review_date','2099-01-01')]:
            row=copy.deepcopy(original);row['evidence']['qualifier_review'][field]=value
            with self.subTest(field=field),self.assertRaises(ValidationError):validate_observation(row,self.data)

    def test_conversion_audit_is_checked(self):
        row=copy.deepcopy(next(o for o in self.data['observations'].values() if o.get('conversion_audit')))
        validate_observation(row,self.data)
        for field,value in [('conversion_factor_to_CNY','100'),('converted_value_CNY','1'),('native_value','1')]:
            bad=copy.deepcopy(row);bad['conversion_audit'][field]=value
            with self.subTest(field=field),self.assertRaises(ValidationError):validate_observation(bad,self.data)

    def test_schema_loaded_from_requested_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(ROOT/'data',root/'data')
            path=root/'data/schema.json';schema=json.loads(path.read_text())
            schema['properties']['reporting_basis']['enum']=['synthetic_test_only']
            path.write_text(json.dumps(schema));data=load(root)
            with self.assertRaisesRegex(ValidationError,'reporting_basis'):validate_observation(self.row,data)

    def test_schema_registry_rule_controls_metric_units(self):
        self.data['schema']['x-atlas-registry-constraints'][0]['allowed_values_field']='time_bases'
        with self.assertRaisesRegex(ValidationError,'unit incompatible'):validate_observation(self.row,self.data)

    def test_unknown_schema_assertion_fails_closed(self):
        self.data['schema']['properties']['value']['unsupported_assertion']=True
        with self.assertRaisesRegex(ValidationError,'unsupported schema keywords'):validate_observation(self.row,self.data)

class ArrayAndStringBoundTests(unittest.TestCase):
    """minItems/maxItems/maxLength are part of the declared vocabulary, so they must assert."""
    def setUp(self):
        from atlas.schema import validate_shape
        self.validate=validate_shape
        def require(cond,message):
            if not cond: raise ValidationError(message)
        self.require=require
        self.schema={'type':'array','minItems':2,'maxItems':3,
                     'items':{'type':'string','minLength':1,'maxLength':4}}

    def test_bounds_accept_a_conforming_array(self):
        self.validate(['ab','cd'],self.schema,self.require)

    def test_bounds_reject_arrays_and_strings_outside_them(self):
        for value in (['ab'],['a','b','c','d'],['ab','toolong'],['ab','']):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                self.validate(value,self.schema,self.require)

    def test_declared_wrap_fragments_must_reassemble_into_the_reported_value(self):
        data=load()
        row=copy.deepcopy(data['observations']['AMEC2022-COMPANY-COST'])
        from atlas.evidence import wrapped_fragments_value,_thousands
        printed=_thousands(row['evidence']['reported_value'])
        cut=max(1,len(printed)//2)
        row['evidence']['page_wrapped_fragments']=[printed[:cut],printed[cut:]]
        self.assertEqual(wrapped_fragments_value(row['evidence']['page_wrapped_fragments']),printed)
        validate_observation(row,data)
        row['evidence']['page_wrapped_fragments']=[printed[:cut],printed[cut:]+'9']
        with self.assertRaises(ValidationError):validate_observation(row,data)

class CoincidentValueTests(unittest.TestCase):
    """One filing can print a fact twice, and separate facts can coincide numerically.
    The declaration records which, because the dimensions cannot distinguish them."""
    def setUp(self):
        self.data=load()
        self.a=copy.deepcopy(self.data['observations']['AMEC2022-COMPANY-COST'])

    def _pair(self):
        b=copy.deepcopy(self.a);b['observation_id']=self.a['observation_id']+'-B'
        data=copy.deepcopy(self.data);data['observations'][b['observation_id']]=b
        return b,data

    def test_a_declaration_against_a_matching_row_is_accepted(self):
        for basis in ('same_fact_restated','distinct_fact_equal_value'):
            with self.subTest(basis=basis):
                b,data=self._pair()
                b['coincident_value']={'counterpart_observation_id':self.a['observation_id'],'basis':basis}
                validate_observation(b,data)

    def test_a_declaration_cannot_point_at_a_row_reporting_a_different_fact(self):
        for field,value in (('value','1'),('unit','CNY_10k'),('metric_id','revenue'),
                            ('source_id','amec_2024'),('entity_id','naura')):
            with self.subTest(field=field):
                b,data=self._pair()
                b['coincident_value']={'counterpart_observation_id':self.a['observation_id'],
                                       'basis':'same_fact_restated'}
                b[field]=value
                with self.assertRaises(ValidationError):validate_observation(b,data)

    def test_a_declaration_cannot_point_at_itself_or_an_unknown_row(self):
        for target in ('AMEC2022-COMPANY-COST-B','no_such_observation'):
            with self.subTest(target=target):
                b,data=self._pair()
                b['coincident_value']={'counterpart_observation_id':target,'basis':'same_fact_restated'}
                with self.assertRaises(ValidationError):validate_observation(b,data)

    def test_the_counterpart_may_not_carry_its_own_declaration(self):
        b,data=self._pair()
        c=copy.deepcopy(b);c['observation_id']=b['observation_id']+'-C'
        data['observations'][c['observation_id']]=c
        data['observations'][b['observation_id']]['coincident_value']={
            'counterpart_observation_id':self.a['observation_id'],'basis':'same_fact_restated'}
        c['coincident_value']={'counterpart_observation_id':b['observation_id'],'basis':'same_fact_restated'}
        with self.assertRaises(ValidationError):validate_observation(c,data)

    def test_every_declaration_on_disk_is_consistent(self):
        obs=self.data['observations']
        declared=[o for o in obs.values() if o.get('coincident_value')]
        self.assertTrue(declared)
        for o in declared:
            other=obs[o['coincident_value']['counterpart_observation_id']]
            self.assertFalse(other.get('coincident_value'))
            self.assertEqual(o['value'],other['value'])
            self.assertEqual(o['source_id'],other['source_id'])
