import copy
import unittest
from atlas.core import load, validate, ValidationError, observation_export
from atlas.entities import entity_ancestors, assert_no_entity_overlap, aggregate_company_financials
from tests.evidence_fixtures import bind_synthetic

class EntityTests(unittest.TestCase):
    def setUp(self):self.data=load()
    def test_missing_parent_self_and_indirect_cycles(self):
        for parent in ['missing','amec','sizone']:
            data=copy.deepcopy(self.data);data['entities']['amec']['parent_entity_id']=parent
            with self.subTest(parent=parent),self.assertRaises(ValidationError):validate(data)
    def test_all_registered_parent_pairs_are_rejected_for_aggregation(self):
        for eid,e in self.data['entities'].items():
            if e.get('parent_entity_id'):
                with self.subTest(entity=eid),self.assertRaisesRegex(ValidationError,'aggregation overlap'):
                    assert_no_entity_overlap([eid,e['parent_entity_id']],self.data['entities'])
    def test_transitive_parent_unknown_and_duplicate_rejected(self):
        entities=copy.deepcopy(self.data['entities']);entities['amec']['parent_entity_id']='naura'
        for ids in [['sizone','naura'],['unknown'],['amec','amec']]:
            with self.subTest(ids=ids),self.assertRaises(ValidationError):assert_no_entity_overlap(ids,entities)
        assert_no_entity_overlap(['amec','hwatsing'],entities)
    def synthetic_pair(self):
        first=copy.deepcopy(self.data['observations']['A2025-CR'])
        first.update(observation_id='SYNTHETIC-A',value='2',unit='CNY_100m',relation='eq')
        first['dimensions']={k:('not_applicable' if v in ('unknown','not_disclosed','') else v) for k,v in first['dimensions'].items()}
        bind_synthetic(first)
        second=copy.deepcopy(first);second.update(observation_id='SYNTHETIC-B',entity_id='naura',value='30000',unit='CNY_10k');bind_synthetic(second)
        self.data['observations'].update({o['observation_id']:o for o in [first,second]})
        return first,second
    def test_exact_subtotal_normalizes_units_and_retains_scope_limit(self):
        rows=self.synthetic_pair();r=aggregate_company_financials([o['observation_id'] for o in rows],self.data)
        self.assertEqual(r['value'],'500000000');self.assertEqual(r['unit'],'CNY')
        self.assertEqual(r['result_kind'],'selected_company_subtotal');self.assertIn('not a market denominator',r['limitations'][0])
    def test_subtotal_rejects_overlap_and_incompatible_inputs(self):
        changes=[{'precision':p} for p in ['approximate','rounded','as_reported_rounded','bounded_as_reported','reported_plan','reported_lower_bound']]+[{'entity_id':'sizone'},{'entity_id':'amec'},{'relation':'approx'},{'unit':'USD'},{'reporting_scope_id':'etch'},
                 {'period':{'start':'2024-01-01','end':'2024-12-31','kind':'annual','basis':'calendar'}},{'metric_id':'operating_cash_flow'}]
        for change in changes:
            rows=self.synthetic_pair();rows[1].update(change)
            with self.subTest(change=change),self.assertRaises(ValidationError):aggregate_company_financials([o['observation_id'] for o in rows],self.data)
    def test_subtotal_rejects_missing_duplicate_pending_and_unknown_basis(self):
        rows=self.synthetic_pair();ids=[o['observation_id'] for o in rows]
        for bad in [[],['missing'],[ids[0],ids[0]]]:
            with self.assertRaises(ValidationError):aggregate_company_financials(bad,self.data)
        rows[1]['evidence']['status']='pending'
        with self.assertRaises(ValidationError):aggregate_company_financials(ids,self.data)
        rows[1]['evidence']['status']='source_checked';rows[1]['dimensions']['geography']='unknown'
        with self.assertRaises(ValidationError):aggregate_company_financials(ids,self.data)
    def test_export_exposes_parent_without_changing_observation(self):
        o=next(o for o in self.data['observations'].values() if o['entity_id']=='sizone');before=copy.deepcopy(o)
        row=observation_export(o,ancestors=entity_ancestors(self.data['entities']))
        self.assertEqual(row['parent_entity_id'],'amec');self.assertEqual(row['ancestor_entity_ids'],'amec');self.assertEqual(o,before)
