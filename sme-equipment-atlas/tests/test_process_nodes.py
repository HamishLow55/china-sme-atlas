import copy
import unittest
from atlas.core import load, validate, validate_observation, ValidationError, observation_export
from tests.evidence_fixtures import bind_synthetic

class ProcessNodeTests(unittest.TestCase):
    def setUp(self):
        self.data=load();self.row=copy.deepcopy(self.data['observations']['A2025-ER']);bind_synthetic(self.row)
        self.row['evidence']['excerpt']+=' Synthetic node-scoped fixture: 28 nm 以下（不含28 nm）, 逻辑器件.'
        self.row['dimensions'].update(process_node='28 nm 以下（不含28 nm）',process_node_context='逻辑器件')
        self.row['reporting_scope_id']='test_node_scope'
        self.data['scopes']['test_node_scope']={'reporting_scope_id':'test_node_scope','category_id':'etch','label':'Synthetic node scope','definition':'Synthetic source table explicitly scoped to the node.','node_scope':{'process_node':self.row['dimensions']['process_node'],'process_node_context':'逻辑器件'}}
    def test_exact_native_expression_and_context_preserved(self):
        validate_observation(self.row,self.data)
        row=observation_export(self.row);self.assertEqual(row['process_node'],'28 nm 以下（不含28 nm）')
        self.row['dimensions']['process_node_context']='not_stated';self.data['scopes']['test_node_scope']['node_scope']['process_node_context']='not_stated';validate_observation(self.row,self.data)
    def test_missing_pair_generic_prose_and_invented_node_rejected(self):
        for mutation in ['missing_context','missing_node','generic','invented','invented_context']:
            row=copy.deepcopy(self.row)
            if mutation=='missing_context':row['dimensions'].pop('process_node_context')
            elif mutation=='missing_node':row['dimensions'].pop('process_node')
            elif mutation=='generic':row['dimensions']['process_node']='先进工艺';row['evidence']['excerpt']+='先进工艺'
            elif mutation=='invented':row['dimensions']['process_node']='3 nm'
            else:row['dimensions']['process_node_context']='DRAM'
            with self.subTest(mutation=mutation),self.assertRaises(ValidationError):validate_observation(row,self.data)
    def test_node_dimensions_are_comparability_boundaries(self):
        row=self.row;row['evidence']['status']='source_checked'
        other=copy.deepcopy(row);other['observation_id']='TEST-NODE';other['dimensions']['process_node']='28 nm'
        self.data['scopes']['test_node_scope_2']=copy.deepcopy(self.data['scopes']['test_node_scope']);self.data['scopes']['test_node_scope_2'].update(reporting_scope_id='test_node_scope_2',node_scope={'process_node':'28 nm','process_node_context':'逻辑器件'});other['reporting_scope_id']='test_node_scope_2'
        self.data['observations'].update({row['observation_id']:row,other['observation_id']:other})
        self.data['series']=[{'series_id':'TEST-NODE','mode':'comparable','observation_ids':[row['observation_id'],other['observation_id']]}]
        with self.assertRaisesRegex(ValidationError,'incompatible observations'):validate(self.data)
    def test_platform_evidence_uses_same_node_contract(self):
        p=next(p for p in self.data['platforms'].values() if p.get('evidence'))
        e=p['evidence'];e['excerpt']+=' Synthetic 7nm logic claim.';e.update(process_node='7nm',process_node_context='logic')
        validate(self.data)
        e['process_node']='5nm'
        with self.assertRaisesRegex(ValidationError,'absent'):validate(self.data)
    def test_named_angstrom_nodes_remain_source_labels(self):
        for label in ['N3E','18A','2纳米','14 Å']:
            row=copy.deepcopy(self.row);row['dimensions']['process_node']=label;row['evidence']['excerpt']+=' '+label
            self.data['scopes']['test_node_scope']['node_scope']['process_node']=label
            validate_observation(row,self.data)

    def test_adjacent_capability_cannot_qualify_generic_revenue(self):
        self.row['reporting_scope_id']='etch'
        with self.assertRaisesRegex(ValidationError,'explicitly node-scoped'):validate_observation(self.row,self.data)
    def test_node_scope_cannot_be_silently_applied_to_unannotated_observations(self):
        self.row['dimensions'].pop('process_node');self.row['dimensions'].pop('process_node_context')
        with self.assertRaisesRegex(ValidationError,'requires node dimensions'):validate_observation(self.row,self.data)
