import unittest
from decimal import Decimal
from atlas.core import reconcile, ValidationError
from atlas.qualifiers import interval, ratio_interval, result_fields, display_result
from tests.test_atlas import synthetic_market

class QualifierTests(unittest.TestCase):
    def test_all_numerator_relations(self):
        for relation,lo,hi,lc,uc in [('gt','50.0000','100.0000',False,True),('ge','50.0000','100.0000',True,True),('lt','0.0000','50.0000',True,False),('le','0.0000','50.0000',True,True),('range','50.0000','75.0000',True,True)]:
            data,n,d,r=synthetic_market();n.update(relation=relation,upper_value='150')
            result=reconcile(r,data)
            with self.subTest(relation=relation):
                self.assertEqual(result['status'],'computed');self.assertIsNone(result['value'])
                self.assertEqual((result['lower_value'],result['upper_value'],result['lower_inclusive'],result['upper_inclusive']),(lo,hi,lc,uc))
    def test_denominator_range_reverses_endpoints(self):
        data,n,d,r=synthetic_market();d.update(relation='range',value='200',upper_value='400')
        result=reconcile(r,data);self.assertEqual((result['lower_value'],result['upper_value']),('25.0000','50.0000'))
    def test_denominator_lower_bound_becomes_open_upper_bound(self):
        data,n,d,r=synthetic_market();d['relation']='gt'
        result=reconcile(r,data)
        self.assertEqual((result['lower_value'],result['upper_value']),('0.0000','50.0000'))
        self.assertFalse(result['lower_inclusive']);self.assertFalse(result['upper_inclusive'])
    def test_denominator_zero_included_blocks_zero_excluded_computes(self):
        for relation,value,upper,expected in [('range','0','200','blocked'),('le','200',None,'blocked'),('gt','0',None,'computed')]:
            data,n,d,r=synthetic_market();d.update(relation=relation,value=value)
            if upper:d['upper_value']=upper
            self.assertEqual(reconcile(r,data)['status'],expected)
    def test_zero_numerator_over_strict_positive_denominator_is_zero(self):
        data,n,d,r=synthetic_market();n['value']='0';d.update(relation='gt',value='0')
        result=reconcile(r,data);self.assertEqual(result['value'],'0.0000');self.assertEqual(result['relation'],'eq')
    def test_approximation_and_precision_do_not_invent_intervals(self):
        for relation,precision in [('approx','as_reported'),('approaching','as_reported'),('eq','approximate'),('eq','rounded'),('eq','as_reported_rounded')]:
            data,n,d,r=synthetic_market();n.update(relation=relation,precision=precision)
            result=reconcile(r,data)
            with self.subTest(relation=relation,precision=precision):
                self.assertEqual(result['relation'],'approx');self.assertTrue(result['approximate'])
                self.assertIsNone(result['lower_value']);self.assertIsNone(result['upper_value'])
                self.assertEqual(display_result(result),'approximately 50%')
    def test_approximate_denominator_propagates_to_bounded_numerator(self):
        data,n,d,r=synthetic_market();n['relation']='gt';d['relation']='approx'
        result=reconcile(r,data);self.assertTrue(result['approximate']);self.assertTrue(display_result(result).startswith('Approximate bounds:'))
    def test_positive_allocation_scales_bounds_and_remains_scenario(self):
        data,n,d,r=synthetic_market();n.update(relation='range',upper_value='150')
        r['adjustments']=[dict(assumption_id='TEST',side='numerator',operation='allocate',factor='0.5',dimension_changes={},rationale='Synthetic',evidence_status='assumed')]
        result=reconcile(r,data);self.assertEqual((result['lower_value'],result['upper_value']),('25.0000','37.5000'))
        self.assertEqual(result['result_kind'],'scenario_estimate')
    def test_bounds_round_outward_and_become_closed_if_extended(self):
        n=interval({'value':'1','relation':'gt'});d=interval({'value':'3','relation':'eq'})
        result=result_fields(ratio_interval(n,d));self.assertEqual(result['lower_value'],'33.3333');self.assertTrue(result['lower_inclusive'])
        n=interval({'value':'1','relation':'lt'})
        result=result_fields(ratio_interval(n,d));self.assertEqual(result['upper_value'],'33.3334');self.assertTrue(result['upper_inclusive'])
    def test_impossible_mix_bound_is_blocked_but_straddling_range_retained(self):
        data,n,d,r=synthetic_market();n.update(value='200',relation='gt')
        self.assertEqual(reconcile(r,data)['status'],'blocked')
        n.update(value='100',relation='range',upper_value='250')
        result=reconcile(r,data);self.assertEqual(result['status'],'computed');self.assertEqual(result['upper_value'],'100.0000');self.assertTrue(result['constraints_applied'])
    def test_qualifiers_never_bypass_scope_gate(self):
        data,n,d,r=synthetic_market();n.update(relation='approx');n['dimensions']['geography']='worldwide'
        result=reconcile(r,data);self.assertEqual(result['status'],'blocked');self.assertIsNone(result['value'])
    def test_implied_size_keeps_unbounded_upper_and_scales_fx(self):
        data,n,d,r=synthetic_market();n.update(relation='gt')
        d.update(metric_id='reported_market_share',unit='percent',value='25',entity_id='amec');r['kind']='implied_market_size'
        r['adjustments']=[dict(assumption_id='TEST-FX',side='numerator',operation='currency_convert',factor='0.1',to_currency='USD',rationale='Synthetic',evidence_status='assumed')]
        result=reconcile(r,data);self.assertEqual(result['unit'],'USD');self.assertEqual(result['lower_value'],'40.0000')
        self.assertIsNone(result['upper_value']);self.assertFalse(result['lower_inclusive']);self.assertNotIn('constraints_applied',result)
    def test_inconsistent_bound_precision_requires_direction(self):
        for precision in ['bounded_as_reported','reported_lower_bound']:
            data,n,d,r=synthetic_market();n['precision']=precision
            result=reconcile(r,data);self.assertEqual(result['status'],'blocked');self.assertIn('explicit relation',result['reasons'][0])
    def test_approaching_anchor_is_explicitly_disclosed(self):
        data,n,d,r=synthetic_market();n['relation']='approaching'
        result=reconcile(r,data);self.assertIn('threshold as an approximate calculation anchor',result['uncertainty_note'])
        self.assertEqual(result['input_qualifiers'][0]['relation'],'approaching')
