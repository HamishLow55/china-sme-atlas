"""Technical evidence units must retain scale, dimension and signed bounds."""
import copy
import unittest
from atlas.core import load, validate_observation, ValidationError

class CapabilityUnitTests(unittest.TestCase):
    def setUp(self):
        self.data=load()
        self.row=copy.deepcopy(self.data['observations']['AMEC2022-COMPANY-COST'])
        self.row.update(observation_id='synthetic-capability-unit-test',metric_id='synthetic_capability',value='281.25',unit='MHz',relation='eq')
        self.row.pop('conversion_audit',None)
        self.row['period']['basis']='period_status'
        self.row['evidence'].update(reported_value='281.25',reported_unit='MHz',excerpt='Synthetic test fixture: 281.25 MHz',status='pending',reviewer='',review_date='')
        self.row['evidence'].pop('conversion',None)
        self.data['metrics']['synthetic_capability']={'metric_id':'synthetic_capability','definition':'Synthetic fixture only','units':['MHz','GHz','Gbps','Celsius','ampere','way'],'time_bases':['period_status'],'allow_negative':True}

    def test_frequency_conversion_requires_exact_scale(self):
        validate_observation(self.row,self.data)
        self.row.update(unit='GHz',value='0.28125')
        self.row['evidence']['conversion']={'operation':'multiply','factor':'0.001'}
        validate_observation(self.row,self.data)
        bad=copy.deepcopy(self.row);bad['evidence']['conversion']['factor']='1'
        with self.assertRaisesRegex(ValidationError,'conversion factor'):validate_observation(bad,self.data)
        bad=copy.deepcopy(self.row);bad['evidence'].pop('conversion')
        with self.assertRaisesRegex(ValidationError,'recorded conversion'):validate_observation(bad,self.data)

    def test_rate_and_frequency_are_different_dimensions(self):
        self.row['unit']='Gbps'
        with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(self.row,self.data)

    def test_signed_temperature_range_requires_both_native_bounds(self):
        self.row.update(unit='Celsius',value='-40',upper_value='125',relation='range')
        self.row['evidence'].update(reported_unit='Celsius',reported_value='-40',reported_upper_value='125',excerpt='Synthetic fixture: -40 to 125 degrees Celsius')
        validate_observation(self.row,self.data)
        self.row['upper_value']='150'
        with self.assertRaisesRegex(ValidationError,'native upper value'):validate_observation(self.row,self.data)

    def test_comparator_multiple_is_not_a_percentage(self):
        self.data['metrics']['synthetic_capability']['units']=['multiple','percent']
        self.row.update(value='1.5',unit='multiple')
        self.row['evidence'].update(reported_value='1.5',reported_unit='multiple',excerpt='Synthetic comparator: 1.5 times')
        validate_observation(self.row,self.data)
        self.row.update(value='150',unit='percent')
        self.row['evidence']['conversion']={'operation':'multiply','factor':'100'}
        self.data['metrics']['synthetic_capability']['units']=['percent']
        self.data['metrics']['synthetic_capability']['percent_semantics']='unbounded_ratio'
        with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(self.row,self.data)

    def test_duration_unit_cannot_be_substituted_for_comparator_multiple(self):
        self.data['metrics']['synthetic_capability']['units']=['year','multiple']
        self.row.update(value='3',unit='year',relation='le')
        self.row['evidence'].update(reported_value='3',reported_unit='year',excerpt='Synthetic planned delivery within 3 years')
        validate_observation(self.row,self.data)
        self.row['unit']='multiple'
        with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(self.row,self.data)

    def test_etch_aspect_ratio_is_not_material_selectivity(self):
        self.data['metrics']['synthetic_capability']['units']=['aspect_ratio','selectivity_ratio']
        self.row.update(value='140',unit='aspect_ratio')
        self.row['evidence'].update(reported_value='140',reported_unit='aspect_ratio',excerpt='Synthetic depth-to-width result 140:1')
        validate_observation(self.row,self.data)
        self.row['unit']='selectivity_ratio'
        with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(self.row,self.data)

    def test_reactors_cannot_be_converted_to_stations_systems_or_models(self):
        alternatives=['reaction_station','system','equipment_model']
        self.data['metrics']['synthetic_capability']['units']=['reactor']+alternatives
        self.row.update(value='300',unit='reactor',relation='gt')
        self.row['evidence'].update(reported_value='300',reported_unit='reactor',excerpt='Synthetic cohort: more than 300 reactors')
        validate_observation(self.row,self.data)
        for unit in alternatives:
            with self.subTest(unit=unit):
                bad=copy.deepcopy(self.row);bad['unit']=unit
                bad['evidence']['conversion']={'operation':'multiply','factor':'1'}
                with self.assertRaisesRegex(ValidationError,'unit dimensions differ'):validate_observation(bad,self.data)
