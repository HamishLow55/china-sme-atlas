import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from atlas.core import ROOT, ValidationError, load, read_json, write_json, digest
from atlas.research import validate_research, coverage, packet, dependency_state, impact, build_research
from atlas.registry import paths, read_records, record_path
from atlas.intake import import_csv, review_page, check_review

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        shutil.copytree(ROOT/'data',self.root/'data');(self.root/'local').mkdir()
    def tearDown(self):self.tmp.cleanup()
    def mutate_target(self,fn):
        p=record_path('coverage_targets','legacy_etch-1',self.root);rows=read_json(p)
        fn(next(row for row in rows if row['target_id']=='legacy_etch-1'));write_json(p,rows)
    def test_found_does_not_imply_exhaustive(self):
        r=coverage(self.root)
        self.assertIn('not the whole',r['scope']);self.assertGreater(len(r['targets']),0)
        self.assertIn('evidenced_periods',r['targets'][0])
    def test_application_excerpt_respects_dataset_restriction(self):
        data=load(self.root)
        a=read_json(paths('application_links',self.root)[0])[0]
        dataset=data['sources'][a['source_id']]['dataset_id']
        data['datasets'][dataset]['git_values_allowed']=False
        with self.assertRaises(ValidationError):validate_research(data,self.root)
    def test_application_review_date_must_be_date(self):
        p=paths('application_links',self.root)[0];rows=read_json(p);rows[0]['review_date']='bad';write_json(p,rows)
        with self.assertRaises(ValueError):validate_research(load(self.root),self.root)
    def test_invalid_target_date_rejected(self):
        self.mutate_target(lambda c:c.update(period_start='2021-99-99'))
        with self.assertRaises(ValueError):validate_research(load(self.root),self.root)
    def test_absent_scope_rejected(self):
        self.mutate_target(lambda c:c.update(reporting_scope_id='missing'))
        with self.assertRaises(ValidationError):validate_research(load(self.root),self.root)
    def test_target_cannot_expand_task_source_set(self):
        self.mutate_target(lambda c:c['reviewed_source_ids'].append('jingyi_inquiry_2024'))
        with self.assertRaises(ValidationError):validate_research(load(self.root),self.root)
    def test_not_found_cannot_link_found_values(self):
        self.mutate_target(lambda c:c.update(status='reviewed_not_found'))
        with self.assertRaises(ValidationError):validate_research(load(self.root),self.root)
    def test_coverage_does_not_accept_partial_flow(self):
        self.mutate_target(lambda c:c.update(period_start='2025-06-01',period_end='2025-12-31'))
        with self.assertRaises(ValidationError):validate_research(load(self.root),self.root)
    def test_packet_retains_definitions_without_observations(self):
        p=self.root/'data/research_tasks.json';rows=read_json(p)
        t=copy.deepcopy(rows[0]);t.update(task_id='empty_task',metric_ids=['market_size'],source_ids=[],category_ids=['etch'])
        rows.append(t);write_json(p,rows)
        packet('empty_task',self.root);p=read_json(self.root/'local/packets/empty_task/packet.json')
        self.assertEqual([],p['existing_observations']);self.assertIn('market_size',p['definitions']['metrics'])
    def test_task_path_traversal_rejected(self):
        p=self.root/'data/research_tasks.json';rows=read_json(p);rows[0]['task_id']='../escape';write_json(p,rows)
        with self.assertRaises(ValidationError):packet('../escape',self.root)
    def test_source_change_reaches_series_and_models(self):
        prior=self.root/'local/prior.json';write_json(prior,dependency_state(self.root))
        p=record_path('sources','amec_2025',self.root);rows=read_json(p)
        next(s for s in rows if s['source_id']=='amec_2025')['notes']+=' corrected'
        write_json(p,rows);r=impact(prior,self.root)
        self.assertIn('reconciliation:amec_2025_portfolio_mix',r['affected'])
        self.assertIn('view:Atlas Coverage View',r['affected'])
    def test_definition_change_reaches_models(self):
        prior=self.root/'local/prior.json';write_json(prior,dependency_state(self.root))
        p=self.root/'data/metrics.json';rows=read_json(p);rows[0]['definition']+=' amended';write_json(p,rows)
        self.assertIn('reconciliation:amec_2025_portfolio_mix',impact(prior,self.root)['affected'])
    def test_platform_source_dependency_is_registered(self):
        state=dependency_state(self.root)
        self.assertIn(['source:jingyi_inquiry_2024','platform:jingyi_skylens_h'],state['edges'])
        self.assertIn(['platform:jingyi_skylens_h','view:Atlas Coverage View'],state['edges'])
    def test_platform_maturity_history_dependency_and_view(self):
        candidate=next(p for p in read_records('platforms',self.root) if p.get('evidence')); path=record_path('platforms',candidate['platform_id'],self.root)
        platforms=read_json(path);p=next(p for p in platforms if p['platform_id']==candidate['platform_id'])
        alternate=next(s for s in load(self.root)['sources'] if s!=p['evidence']['source_id'])
        p['maturity_history']=[{'source_id':alternate,'page':1,'excerpt':'Synthetic later milestone',
            'status':'pending','reviewer':'','review_date':'','reported_maturity':'batch_orders',
            'as_of':'2026-06-30','claim_kind':'company_reported','notes':'Fixture limitation.'}]
        write_json(path,platforms)
        state=dependency_state(self.root)
        self.assertIn(['source:'+alternate,'platform:'+p['platform_id']],state['edges'])
        build_research(self.root)
        view=(self.root/'build/Atlas Coverage View.md').read_text()
        self.assertIn('## Platform Maturity Evidence',view);self.assertIn('batch_orders',view)
    def test_report_context_maturity_does_not_invent_a_date(self):
        from atlas.core import validate
        data=load(self.root)
        platform=next(p for p in data['platforms'].values() if p.get('evidence'))
        history={'source_id':platform['evidence']['source_id'],'page':1,'excerpt':'Synthetic undated validation claim',
                 'status':'pending','reviewer':'','review_date':'','reported_maturity':'customer_validation',
                 'as_of':'','date_basis':'source_report_context','claim_kind':'company_reported','notes':'Synthetic report-context fixture.'}
        platform['maturity_history']=[history]
        validate(data)
        history['as_of']='2026-03-31'
        with self.assertRaisesRegex(ValidationError,'must not assign'):validate(data)
        history.update(as_of='',date_basis='invented')
        with self.assertRaisesRegex(ValidationError,'date basis'):validate(data)
        history.update(date_basis='source_stated_date')
        with self.assertRaises((ValueError,ValidationError)):validate(data)
        history.update(as_of='2026-03-31')
        validate(data)
    def test_report_context_maturity_view_names_source(self):
        candidate=next(p for p in read_records('platforms',self.root) if p.get('evidence'))
        path=record_path('platforms',candidate['platform_id'],self.root);rows=read_json(path)
        p=next(p for p in rows if p['platform_id']==candidate['platform_id'])
        sid=p['evidence']['source_id']
        p['maturity_history']=[{'source_id':sid,'page':1,'excerpt':'Synthetic undated claim','status':'pending',
            'reviewer':'','review_date':'','reported_maturity':'in_validation','as_of':'',
            'date_basis':'source_report_context','claim_kind':'company_reported','notes':'Synthetic fixture.'}]
        write_json(path,rows);build_research(self.root)
        view=(self.root/'build/Atlas Coverage View.md').read_text()
        self.assertIn('Report context: '+load(self.root)['sources'][sid]['title'],view)
    def test_csv_intake_cannot_self_approve(self):
        o=copy.deepcopy(next(iter(load(self.root)['observations'].values())))
        o['value']='123'
        from tests.evidence_fixtures import bind_synthetic
        bind_synthetic(o)
        csv=self.root/'local/input.csv';csv.write_text('id,value\nPROPOSAL-1,123\n')
        mapping=self.root/'local/mapping.json';write_json(mapping,{'template':o,'columns':{'observation_id':'id','value':'value'}})
        out=self.root/'local/proposal.json';import_csv(csv,mapping,out,self.root)
        self.assertEqual(read_json(out)[0]['evidence']['status'],'pending')
        self.assertNotIn('PROPOSAL-1',load(self.root)['observations'])
    def test_review_bound_to_exact_batch(self):
        batch=self.root/'local/batch.json';o=next(iter(load(self.root)['observations'].values()));write_json(batch,[o])
        p=self.root/'local/decisions.json';write_json(p,{'batch_sha256':'wrong','reviewer':'test','review_date':'2026-09-21','decisions':[]})
        with self.assertRaises(ValidationError):check_review(batch,p)
    def replay_fixture(self):
        row=copy.deepcopy(next(iter(load(self.root)['observations'].values())))
        row['conversion_audit']={'converted_value_CNY':'100.0000001'}
        held=copy.deepcopy(row);held['observation_id']='TEST-HELD'
        batch=self.root/'local/replay_batch.json';write_json(batch,[row,held])
        decisions=self.root/'local/replay_decisions.json'
        write_json(decisions,{'batch_sha256':digest(batch),'reviewer':'test','review_date':'2026-09-22','decisions':[
            {'observation_id':row['observation_id'],'decision':'correct','notes':'Synthetic nested audit correction.',
             'corrections':[{'field':'conversion_audit.converted_value_CNY','value':'100'}]},
            {'observation_id':held['observation_id'],'decision':'hold','notes':'Synthetic unsupported value.'}]})
        corrected=self.root/'local/replay_corrected.json';row['conversion_audit']['converted_value_CNY']='100'
        write_json(corrected,[row])
        return batch,decisions,corrected
    def test_review_replay_checks_nested_patch_without_mutation(self):
        paths=self.replay_fixture();before=[p.read_bytes() for p in paths]
        result=check_review(*paths)
        self.assertEqual(result['replay'],'exact_match');self.assertEqual(result['corrected_observations'],1)
        self.assertFalse(result['integrated']);self.assertEqual(before,[p.read_bytes() for p in paths])
    def test_review_replay_requires_consistent_decision_and_patches(self):
        batch,decisions,corrected=self.replay_fixture();review=read_json(decisions)
        review['decisions'][0]['decision']='accept';write_json(decisions,review)
        with self.assertRaisesRegex(ValidationError,'Correct decisions need patches'):
            check_review(batch,decisions,corrected)
        review['decisions'][0]['decision']='correct';review['decisions'][0]['corrections']=[]
        write_json(decisions,review);write_json(corrected,[read_json(batch)[0]])
        with self.assertRaisesRegex(ValidationError,'Correct decisions need patches'):
            check_review(batch,decisions,corrected)
    def test_review_replay_rejects_missing_patch(self):
        batch,decisions,corrected=self.replay_fixture();review=read_json(decisions)
        review['decisions'][0]['corrections']=[];review['decisions'][0]['decision']='accept';write_json(decisions,review)
        with self.assertRaisesRegex(ValidationError,'differs from review patch replay'):
            check_review(batch,decisions,corrected)
    def test_review_replay_rejects_held_row_and_duplicate(self):
        batch,decisions,corrected=self.replay_fixture();rows=read_json(corrected)
        for extra in (read_json(batch)[1],rows[0]):
            with self.subTest(extra=extra['observation_id']):
                write_json(corrected,rows+[extra])
                with self.assertRaises(ValidationError):check_review(batch,decisions,corrected)
    def test_review_replay_rejects_invalid_path_and_protected_input(self):
        batch,decisions,corrected=self.replay_fixture();review=read_json(decisions)
        review['decisions'][0]['corrections'][0]['field']='missing.nested.value';write_json(decisions,review)
        with self.assertRaises(ValidationError):check_review(batch,decisions,corrected)
        with self.assertRaises(ValidationError):check_review(batch,decisions,self.root/'Semis notes/corrected.json')
    def test_review_escapes_untrusted_excerpt(self):
        o=copy.deepcopy(next(iter(load(self.root)['observations'].values())))
        o['evidence']['excerpt']='<script>alert(1)</script>'
        p=self.root/'local/batch.json';write_json(p,[o]);out=review_page(p,self.root)
        text=Path(out['review_page']).read_text();self.assertIn('&lt;script&gt;',text);self.assertNotIn('<script>alert(1)',text)
    def test_protected_intake_path_rejected(self):
        p=self.root/'Semis notes/batch.json'
        with self.assertRaises(ValidationError):review_page(p,self.root)
    def test_legacy_batch_protected_path_rejected(self):
        from atlas.cli import check_batch
        with self.assertRaises(ValidationError):check_batch(self.root/'Semis notes/batch.json')
    def test_batch_stages_new_source_without_writing_registries(self):
        from atlas.cli import check_batch
        data=load();o=copy.deepcopy(data['observations']['A2025-ER'])
        source=copy.deepcopy(data['sources'][o['source_id']]);source['source_id']='synthetic_source'
        o.update(observation_id='SYNTHETIC-STAGED',source_id=source['source_id'])
        batch=self.root/'local/batch.json';registry=self.root/'local/registries.json'
        write_json(batch,[o]);write_json(registry,{'sources':[source]})
        before={str(p):digest(p) for p in paths('sources')}
        self.assertTrue(check_batch(batch,registry)['registries_staged'])
        self.assertEqual(before,{str(p):digest(p) for p in paths('sources')})
        with self.assertRaises(ValidationError):check_batch(batch)
    def test_batch_rejects_metric_safeguard_removal(self):
        from atlas.cli import check_batch
        data=load();o=copy.deepcopy(data['observations']['A2025-ER']);o['observation_id']='SYNTHETIC-STAGED'
        metric=copy.deepcopy(data['metrics']['operating_cash_flow']);metric.pop('allow_negative')
        batch=self.root/'local/batch.json';registry=self.root/'local/registries.json'
        write_json(batch,[o]);write_json(registry,{'metrics':[metric]})
        with self.assertRaisesRegex(ValidationError,'replace an existing definition'):check_batch(batch,registry)
    def test_batch_reports_each_invalid_row_and_protects_registry_path(self):
        from atlas.cli import check_batch
        data=load();a=copy.deepcopy(data['observations']['A2025-ER']);b=copy.deepcopy(a)
        a.update(observation_id='SYNTHETIC-ONE',value='NaN');b.update(observation_id='SYNTHETIC-TWO',value='-1')
        batch=self.root/'local/batch.json';write_json(batch,[{},None,a,b])
        with self.assertRaises(ValidationError) as caught:check_batch(batch)
        self.assertIn('SYNTHETIC-ONE',str(caught.exception));self.assertIn('SYNTHETIC-TWO',str(caught.exception))
        self.assertIn('Row 1',str(caught.exception));self.assertIn('Row 2',str(caught.exception))
        with self.assertRaises(ValidationError):check_batch(batch,self.root/'Semis notes/registries.json')
        registry=self.root/'local/registries.json';write_json(registry,{'sources':[{}]})
        with self.assertRaisesRegex(ValidationError,'nonempty source_id'):check_batch(batch,registry)
    def test_publisher_protected_root_rejected_before_build(self):
        from atlas.cli import publish
        with self.assertRaises(ValidationError):publish(self.root/'Semis notes',False)
    def test_review_refuses_mismatched_original(self):
        o=copy.deepcopy(next(iter(load(self.root)['observations'].values())))
        original=self.root/'local/wrong.pdf';original.write_text('not the registered original')
        write_json(self.root/'local/source_paths.json',{o['source_id']:str(original)})
        batch=self.root/'local/batch.json';write_json(batch,[o]);out=review_page(batch,self.root)
        self.assertIn('Original unresolved',Path(out['review_page']).read_text())

class ExpansionRegressions(unittest.TestCase):
    def test_hwatsing_scope_changes_are_not_comparable_cmp_series(self):
        d=load();obs=[d['observations'][f'H{y}-SEGREV'] for y in (2023,2024,2025)]
        self.assertEqual(len({o['reporting_scope_id'] for o in obs}),3)
        self.assertEqual(obs[0]['category_id'],'cmp');self.assertEqual(obs[1]['category_id'],'multi_equipment')
    def test_ordinal_milestone_is_lower_bound(self):
        d=load()['observations'];self.assertEqual(d['H2024-CMP500']['relation'],'ge')
        self.assertEqual(d['H2026-CMP1000']['relation'],'ge')
        self.assertNotEqual(d['H2024-CMP500']['reporting_scope_id'],d['H2026-CMP1000']['reporting_scope_id'])
    def test_naura_revenue_bound_not_zero_or_exact(self):
        o=load()['observations']['N2025-ER'];self.assertEqual((o['value'],o['unit'],o['relation']),('100','CNY_100m','gt'))
    def test_acm_mixed_revenue_not_ecp_or_tsv(self):
        o=load()['observations']['ACMR2025-EF-REV'];self.assertEqual(o['category_id'],'multi_equipment')
        self.assertEqual(o['reporting_scope_id'],'acmr_ecp_furnace_other')

if __name__=='__main__':unittest.main()
