"""Partition integrity and bounded-write regressions on disposable copies."""
import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from atlas.core import ROOT, ValidationError, load, validate, read_json, write_json, digest
from atlas.registry import paths, read_records, record_path, write_partition, validate_partition_owners
from atlas.research import dependency_state, impact

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        shutil.copytree(ROOT/'data',self.root/'data')
    def tearDown(self):self.tmp.cleanup()
    def _entity_owned_source(self):
        """A source whose partition is an entity, not _shared.

        _shared legitimately holds sources whose dataset publisher is not an atlas entity, such as
        third-party reference data, so these tests must not assume that partition is empty."""
        for row in read_records('sources',self.root):
            if record_path('sources',row['source_id'],self.root).stem!='_shared':return row
        self.fail('no entity-owned source to test with')

    def test_duplicate_across_partitions_rejected(self):
        row=self._entity_owned_source()
        p=self.root/'data/sources/_shared.json'
        rows=read_json(p) if p.exists() else []
        write_json(p,rows+[row])
        with self.assertRaisesRegex(ValidationError,'duplicate registry ID'):load(self.root)
    def test_direct_entity_mismatch_rejected(self):
        p=self.root/'data/entities/amec.json';rows=read_json(p);rows[0]['entity_id']='different';write_json(p,rows)
        with self.assertRaisesRegex(ValidationError,'differs from partition'):load(self.root)
    def test_unknown_owner_and_legacy_monolith_rejected(self):
        p=self.root/'data/sources/unknown.json';write_json(p,[])
        with self.assertRaisesRegex(ValidationError,'unknown partition owner'):validate_partition_owners(self.root)
        p.unlink();write_json(self.root/'data/sources.json',[])
        with self.assertRaisesRegex(ValidationError,'legacy monolith'):load(self.root)
    def test_unresolved_claim_duplicates_checked_by_validator(self):
        row=read_records('unresolved_claims',self.root)[0]
        owner=record_path('unresolved_claims',row.get('claim_id',row.get('candidate_id')),self.root).stem
        p=self.root/'data/unresolved_claims'/('naura.json' if owner!='naura' else 'amec.json')
        rows=read_json(p) if p.exists() else [];write_json(p,rows+[row])
        with self.assertRaisesRegex(ValidationError,'duplicate registry ID'):validate(load(self.root),self.root)
    def test_unsafe_layout_rejected(self):
        p=self.root/'data/sources/amec.json';p.unlink();p.symlink_to(ROOT/'data/sources/amec.json')
        with self.assertRaisesRegex(ValidationError,'unsafe or missing'):load(self.root)
        p.unlink();(self.root/'data/sources/nested').mkdir()
        with self.assertRaisesRegex(ValidationError,'nested or non-JSON'):load(self.root)
    def test_writer_changes_only_owned_file_and_detects_stale_version(self):
        p=self.root/'data/sources/amec.json';before={q:digest(q) for q in self.root.glob('data/**/*.json')}
        rows=read_json(p);rows[0]['notes']+=' Synthetic mutation.'
        write_partition('sources','amec',rows,self.root,expected_sha256=before[p])
        self.assertEqual([p],[q for q,h in before.items() if digest(q)!=h])
        with self.assertRaisesRegex(ValidationError,'Partition changed'):write_partition('sources','amec',rows,self.root,expected_sha256=before[p])
        with self.assertRaisesRegex(ValidationError,'hash missing'):write_partition('sources','amec',rows,self.root)
    def test_writer_rejects_owner_traversal_duplicates_and_other_owner_ids(self):
        rows=[self._entity_owned_source()]
        for owner in ['../escape','unknown']:
            with self.subTest(owner=owner),self.assertRaises(ValidationError):write_partition('sources',owner,rows,self.root)
        shared=self.root/'data/sources/_shared.json'
        h=digest(shared) if shared.exists() else None
        with self.assertRaisesRegex(ValidationError,'Duplicate IDs'):write_partition('sources','_shared',rows*2,self.root,expected_sha256=h)
        with self.assertRaisesRegex(ValidationError,'another partition'):write_partition('sources','_shared',rows,self.root,expected_sha256=h)
    def test_writer_new_entity_partition_is_explicit(self):
        rows=copy.deepcopy(read_records('entities',self.root)[:1]);rows[0]['entity_id']='synthetic_entity'
        p=write_partition('entities','synthetic_entity',rows,self.root)
        self.assertEqual(p,self.root/'data/entities/synthetic_entity.json')
        self.assertEqual(read_json(p),rows)
    def test_derived_ownership_rejects_valid_but_wrong_owner(self):
        for name,rid in [('sources','amec_2025'),('datasets','amec_annual_disclosures'),('series','amec_etch_revenue')]:
            with self.subTest(registry=name):
                src=record_path(name,rid,self.root);old=read_json(src)
                row=next(r for r in old if rid in r.values());dest=self.root/f'data/{name}/naura.json';other=read_json(dest)
                write_json(src,[r for r in old if r!=row]);write_json(dest,other+[row])
                with self.assertRaisesRegex(ValidationError,'derived partition owner'):validate_partition_owners(self.root)
                write_json(src,old);write_json(dest,other)
    def test_writer_rejects_deletion_and_derived_misownership(self):
        p=self.root/'data/sources/amec.json';rows=read_json(p)
        with self.assertRaisesRegex(ValidationError,'cannot remove'):write_partition('sources','amec',rows[:-1],self.root,expected_sha256=digest(p))
        row=copy.deepcopy(rows[0]);row['source_id']='synthetic_source'
        with self.assertRaisesRegex(ValidationError,'derived partition owner'):write_partition('sources','market',[row],self.root)
    def test_cross_entity_originals_remain_valid(self):
        data=load(self.root);validate(data,self.root)
        row=next(o for o in data['observations'].values() if o['entity_id']=='kingstone_semiconductor')
        self.assertNotEqual(record_path('sources',row['source_id'],self.root).stem,row['entity_id'])
    def test_source_change_does_not_invalidate_unrelated_firm(self):
        prior=self.root/'local/prior.json';write_json(prior,dependency_state(self.root))
        p=record_path('sources','amec_2025',self.root);rows=read_json(p)
        next(r for r in rows if r['source_id']=='amec_2025')['notes']+=' Synthetic correction.';write_json(p,rows)
        affected=impact(prior,self.root)['affected']
        self.assertIn('observation:A2025-ER',affected)
        self.assertNotIn('observation:N2025-ER',affected)
