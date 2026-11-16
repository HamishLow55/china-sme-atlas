"""Research scope, agent packets, retrieval evaluation and change impact.

Coverage is declared against named sources; retrieved hits never promote it.
Research packets and source excerpts are local outputs, not Git inputs.
"""
import hashlib
import json
import re
from pathlib import Path
from .core import ROOT, read_json, write_json, require, index, load, table, input_hashes, valid_date, digest, source_link

from .registry import read_records

FILES = {'applications': 'application_id', 'application_links': 'link_id',
         'research_tasks': 'task_id', 'coverage_targets': 'target_id'}

def registries(root=ROOT):
    from .registry import read_records
    return {name:index(read_records(name,root),key) for name,key in FILES.items()}

def validate_research(data, root=ROOT):
    from .reviews import validate_reviews
    validate_reviews(data, root)
    r=registries(root)
    for a in r['application_links'].values():
        require(a['application_id'] in r['applications'], 'Unknown application')
        require(a['entity_id'] in data['entities'] and a['category_id'] in data['categories'], 'Unknown application entity/category')
        require(a['source_id'] in data['sources'] and int(a['page'])>0 and a['excerpt'], 'Application needs source and passage')
        require(data['datasets'][data['sources'][a['source_id']]['dataset_id']]['git_values_allowed'] is True,'Application excerpt not permitted in repository')
        require(a['status'] in {'pending','source_checked'}, 'Invalid application review status')
        if a.get('platform_id'):
            p=data['platforms'].get(a['platform_id'])
            require(p and p['entity_id']==a['entity_id'] and p['category_id']==a['category_id'], 'Application platform mismatch')
        require(a.get('scope_note'), 'Application mapping needs scope limitation')
        require(a.get('link_kind') in {'process_relevance','supplier_capability','production_claim'},'Application needs explicit claim type')
        require(a['status']!='source_checked' or (a.get('reviewer') and a.get('review_date')),'Checked application needs review provenance')
        if a.get('review_date'):valid_date(a['review_date'])
    for task in r['research_tasks'].values():
        require(re.fullmatch(r'[a-z0-9_-]+',task['task_id']), 'Unsafe task ID')
        require(task['question'] and task['acceptance_criteria'] and task['stop_rule'], 'Task needs bounded acceptance and stop rule')
        for field,reg in [('entity_ids','entities'),('category_ids','categories'),('metric_ids','metrics'),('source_ids','sources')]:
            require(all(i in data[reg] for i in task[field]), 'Unknown task '+field)
        valid_date(task['period_start']);valid_date(task['period_end'])
        require(task['period_start']<=task['period_end'],'Reversed task period')
    for c in r['coverage_targets'].values():
        for field,reg in [('entity_id','entities'),('category_id','categories'),('metric_id','metrics')]:
            require(c[field] in data[reg], 'Unknown coverage '+field)
        require(c['task_id'] in r['research_tasks'], 'Unknown coverage task')
        task=r['research_tasks'][c['task_id']]
        for singular,plural in [('entity_id','entity_ids'),('category_id','category_ids'),('metric_id','metric_ids')]:
            require(not task[plural] or c[singular] in task[plural], 'Target outside assigned task scope')
        if c.get('reporting_scope_id'):
            require(c['reporting_scope_id'] in data['scopes'] and data['scopes'][c['reporting_scope_id']]['category_id']==c['category_id'],'Unknown or mismatched target reporting scope')
        if c.get('platform_id'):
            p=data['platforms'].get(c['platform_id'])
            require(p and p['entity_id']==c['entity_id'] and p['category_id']==c['category_id'],'Unknown or mismatched target platform')
        require(c['status'] in {'not_searched','reviewed_found','reviewed_not_found','conflicting','unresolved'}, 'Invalid target status')
        valid_date(c['period_start']);valid_date(c['period_end'])
        require(task['period_start']<=c['period_start']<=c['period_end']<=task['period_end'], 'Target dates outside task')
        require(all(s in data['sources'] for s in c['reviewed_source_ids']), 'Unknown reviewed source')
        require(set(c['reviewed_source_ids'])<=set(task['source_ids']),'Coverage source set exceeds task assignment')
        require(c['status'] not in {'reviewed_found','reviewed_not_found'} or c['reviewed_source_ids'], 'Reviewed target needs source set')
        for oid in c['observation_ids']:
            o=data['observations'].get(oid)
            require(o and matches(o,c), 'Coverage observation does not match target')
            require(o['source_id'] in c['reviewed_source_ids'], 'Coverage observation source not reviewed')
        require(c['status']!='reviewed_found' or c['observation_ids'], 'Found target needs explicit observations')
        require(c['status']!='reviewed_not_found' or not c['observation_ids'], 'Not-found target cannot contain observations')
    return r

def matches(o,c):
    return (all(o[k]==c[k] for k in ('entity_id','category_id','metric_id'))
            and c['period_start']<=o['period']['end']<=c['period_end']
            and (not o['period'].get('start') or c['period_start']<=o['period']['start'])
            and (not c.get('reporting_scope_id') or c['reporting_scope_id']==o['reporting_scope_id'])
            and (not c.get('platform_id') or c['platform_id']==o['platform_id'])
            and all(o['dimensions'].get(k)==v for k,v in c.get('dimensions',{}).items()))

def coverage(root=ROOT):
    data=load(root); r=validate_research(data,root); rows=[]
    for c in r['coverage_targets'].values():
        accepted=[data['observations'][oid] for oid in c['observation_ids'] if data['observations'][oid]['evidence']['status']=='source_checked']
        rows.append({**c,'accepted_observation_count':len(accepted),
                     'evidenced_periods':sorted({(o['period'].get('start')+' to ' if o['period'].get('start') else 'as of ')+o['period']['end'] for o in accepted})})
    return {'scope':'Declared targets and named reviewed source sets only; not the whole Chinese equipment landscape.',
            'targets':rows,'status_counts':{s:sum(c['status']==s for c in rows) for s in sorted({c['status'] for c in rows})}}

def alias_map(data):
    aliases={}
    for registry in ('entities','platforms','categories'):
        for key,row in data[registry].items():
            aliases[key]=list(dict.fromkeys([key,row['name']]+row.get('aliases',[])))
    return aliases

def packet(task_id,root=ROOT):
    from .library import search_library
    data=load(root);r=validate_research(data,root)
    require(task_id in r['research_tasks'],'Unknown research task')
    task=r['research_tasks'][task_id]
    observations=[o for o in data['observations'].values() if
        (not task['entity_ids'] or o['entity_id'] in task['entity_ids']) and
        (not task['category_ids'] or o['category_id'] in task['category_ids']) and
        (not task['metric_ids'] or o['metric_id'] in task['metric_ids']) and
        o['source_id'] in task['source_ids'] and
        task['period_start']<=o['period']['end']<=task['period_end'] and
        (not o['period'].get('start') or task['period_start']<=o['period']['start']) and
        (not task.get('platform_ids') or o['platform_id'] in task['platform_ids'])]
    hits={}; warnings=[]
    if (root/'local/library.sqlite').exists():
        for q in task.get('queries',[]):hits[q]=search_library(q,root/'local',aliases=alias_map(data),limit=5)
    else:warnings.append('Local page library absent; run library-index first. Empty retrieval is not evidence of absence.')
    paths=read_json(root/'local/source_paths.json') if (root/'local/source_paths.json').exists() else {}
    from .library import _allowed
    sources=[]
    for sid in task['source_ids']:
        p=Path(paths[sid]) if sid in paths else None
        available=bool(p and _allowed(p) and p.is_file() and digest(p)==data['sources'][sid]['sha256'])
        sources.append({**data['sources'][sid],'local_path':str(p) if available else None,'available_locally':available})
    result={'task':task,'input_hashes':input_hashes(root),'sources':sources,'existing_observations':observations,
            'definitions':{reg:{k:v for k,v in data[reg].items() if k in {o[field] for o in observations}|set(task.get(field.replace('_id','_ids'),[]))}
                           for reg,field in [('metrics','metric_id'),('scopes','reporting_scope_id'),('categories','category_id'),('platforms','platform_id')]},
            'coverage':[c for c in coverage(root)['targets'] if c['task_id']==task_id],
            'application_links':[a for a in r['application_links'].values() if a['entity_id'] in task['entity_ids'] and a['source_id'] in task['source_ids'] and (not task['category_ids'] or a['category_id'] in task['category_ids'])],
            'retrieval_hits':hits,'warnings':warnings,
            'rules':['Open original passages; analysis and search snippets are leads.', 'Record failed searches with named source sets.',
                     'No assumption that all category revenue belongs to one application.', 'Propose separate batches; verifier checks originals before integration.']}
    out=root/'local/packets'/task_id;out.mkdir(parents=True,exist_ok=True)
    write_json(out/'packet.json',result)
    text=['# '+task['title'],'',task['question'],'','## Completion Criteria','']+['- '+x for x in task['acceptance_criteria']]
    text+=['','Stop rule: '+task['stop_rule'],'','## Sources','',table(['ID','Title','Local original'],[[s['source_id'],s['title'],s['local_path'] or 'unresolved'] for s in sources]),'',
           'Full observations, definitions, coverage, local search passages and input hashes are in `packet.json`. Search results do not constitute review.']
    (out/'Packet.md').write_text('\n'.join(text)+'\n')
    return {'task_id':task_id,'packet':str(out),'observations':len(observations),'sources':len(sources),'warnings':warnings}

def evaluate_retrieval(root=ROOT):
    from .library import search_library
    cases=read_json(root/'data/retrieval_cases.json');results=[]
    for c in cases:
        hits=search_library(c['query'],root/'local',aliases=alias_map(load(root)),limit=c.get('limit',10))
        good=[h for h in hits if c['expected_source_id'] in h.get('source_ids',[h.get('source_id')]) and
              (not c.get('expected_pages') or h['page'] in c['expected_pages'])]
        results.append({'case_id':c['case_id'],'passed':bool(good),'query':c['query'],'returned':len(hits)})
    return {'passed':sum(x['passed'] for x in results),'total':len(results),'cases':results,
            'limitation':'Recall on this reviewed benchmark only; not comprehensive discovery or evidence verification.'}

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def dependency_state(root=ROOT):
    data=load(root);nodes={};edges=[]
    for group,key in [('sources','source'),('observations','observation')]:
        for id,row in data[group].items():nodes[key+':'+id]=fingerprint(row)
    for oid,o in data['observations'].items():edges.append(['source:'+o['source_id'],'observation:'+oid])
    r=registries(root)
    for p in data['platforms'].values():
        if p.get('evidence') or p.get('maturity_history'):
            node='platform:'+p['platform_id'];nodes[node]=fingerprint(p)
            if p.get('evidence'):edges.append(['source:'+p['evidence']['source_id'],node])
            edges.extend(['source:'+h['source_id'],node] for h in p.get('maturity_history',[]))
            edges.append([node,'view:Atlas Coverage View'])
    for a in r['application_links'].values():
        node='application_link:'+a['link_id'];nodes[node]=fingerprint(a)
        edges.extend([['source:'+a['source_id'],node],[node,'view:Atlas Coverage View']])
    for c in r['coverage_targets'].values():
        node='coverage_target:'+c['target_id'];nodes[node]=fingerprint(c)
        edges.extend(['observation:'+oid,node] for oid in c['observation_ids'])
        edges.extend(['source:'+sid,node] for sid in c['reviewed_source_ids'])
        edges.append([node,'view:Atlas Coverage View'])
    for s in data['series']:
        node='series:'+s['series_id'];nodes[node]=fingerprint(s)
        edges.extend(['observation:'+oid,node] for oid in s['observation_ids'])
        edges.append([node,'view:Atlas Data View'])
    for r in data['reconciliations']:
        node='reconciliation:'+r['reconciliation_id'];nodes[node]=fingerprint(r)
        edges.extend(['observation:'+r[k],node] for k in ('numerator_id','denominator_id') if r.get(k))
        edges.append([node,'view:Atlas Reconciliation View'])
    for p,h in input_hashes(root).items():
        if p not in {'data/sources.json','data/series.json','data/reconciliations.json'} and not p.startswith(('data/observations/','data/sources/','data/series/')):
            node='input:'+p;nodes[node]=h
            edges.extend([[node,'view:Atlas Data View'],[node,'view:Atlas Reconciliation View'],[node,'view:Atlas Coverage View']])
            # Conservative invalidation: changing shared definitions/code may
            # change every interpretation, even when numeric rows are unchanged.
            edges.extend([node,'observation:'+oid] for oid in data['observations'])
    return {'nodes':nodes,'edges':edges}

def impact(previous,root=ROOT):
    old=read_json(previous);new=dependency_state(root)
    changed={k for k in set(old['nodes'])|set(new['nodes']) if old['nodes'].get(k)!=new['nodes'].get(k)}
    affected=set(changed);edges=old['edges']+new['edges']
    while True:
        more={b for a,b in edges if a in affected}-affected
        if not more:break
        affected|=more
    return {'changed':sorted(changed),'affected':sorted(affected),'limitation':'Registered structured dependencies only; freeform Obsidian prose is not automatically tracked.'}

def build_research(root=ROOT, *, dependencies=False):
    data=load(root);r=validate_research(data,root);report=coverage(root);out=root/'build'
    write_json(out/'coverage.json',report)
    if dependencies:
        write_json(out/'dependencies.json',dependency_state(root))
    else:
        (out/'dependencies.json').unlink(missing_ok=True)
    maturity_rows=[(p,h) for p in data['platforms'].values() for h in p.get('maturity_history',[])]
    text=['# Atlas Coverage and Research Queue','',report['scope'],'','## Declared Coverage','',
          table(['Company','Category / scope','Metric','Target interval','Evidenced periods','Status','Accepted','Next action'],
                [[c['entity_id'],c.get('reporting_scope_id') or c['category_id'],c['metric_id'],c['period_start']+'–'+c['period_end'],'; '.join(c['evidenced_periods']) or 'none',c['status'],c['accepted_observation_count'],c['next_action']] for c in report['targets']]),
          '','## Research Tasks','',table(['Task','Question','Stop rule'],[[t['task_id'],t['question'],t['stop_rule']] for t in r['research_tasks'].values()]),
          '','## Application Evidence','', 'Application links do not allocate company or category revenue to TSV, HBM or another application.','',
          table(['Application','Entity / platform','Claim type','Review status','Source','Scope limitation'],[[a['application_id'],a.get('platform_id') or a['entity_id'],a['link_kind'],a['status'],source_link({'source_id':a['source_id'],'evidence':{'page':a['page']}},data),a['scope_note']] for a in r['application_links'].values()]),
          '', '## Platform Landscape', '', 'Maturity labels describe what the cited historical document reports, not independently established current status. Platform rows without direct evidence are navigation entries only.', '',
          table(['Company','Platform','Category','Reported stage','Review status','Document date','Source','Limits'],
                [[p['entity_id'],p['name'],p['category_id'],p.get('reported_maturity','not_assessed'),p['evidence']['status'],
                  data['sources'][p['evidence']['source_id']].get('publication_date') or 'unknown',
                  source_link({'source_id':p['evidence']['source_id'],'evidence':p['evidence']},data),p.get('notes','')]
                 for p in data['platforms'].values() if p.get('evidence')]),
          '', '## Platform Maturity Evidence', '', 'These claims preserve company-reported stages. Report-context entries have no source-stated milestone date; legacy dates retain their original interpretation.', '',
          table(['Company','Platform','Date or report context','Reported stage','Review status','Source','Limits'],
                [[p['entity_id'],p['name'],('Report context: '+data['sources'][h['source_id']]['title']) if h.get('date_basis')=='source_report_context' else h['as_of'],h['reported_maturity'],h['status'],
                  source_link({'source_id':h['source_id'],'evidence':{'page':h['page']}},data),h['notes']]
                 for p,h in maturity_rows]),
          '', '## Unresolved Evidence', '',table(['Claim / lead','Reason'],[[h.get('claim',h.get('claim_id','')),h.get('reason',h.get('notes',''))] for h in read_records('unresolved_claims',root) if h.get('status')!='resolved'])]
    direct_counts={cid:sum(o['category_id']==cid for o in data['observations'].values()) for cid in data['categories']}
    text+=['','## Category Map','','Research boundaries only. Counts are direct observation assignments, not supplier capability, market coverage or additive totals. Method and process categories can overlap.','',
           table(['Category','Parent','Direct observations','Definition / boundary'],
                 [[c['name'],c.get('parent_category_id') or '—',direct_counts[cid],c.get('definition','')+' '+c.get('scope_note','')] for cid,c in data['categories'].items()])]
    node_rows=[(p,e) for p in data['platforms'].values() for e in ([p['evidence']] if p.get('evidence') else [])+p.get('maturity_history',[]) if e.get('process_node')]
    if node_rows:
        text+=['','## Source-Reported Process Nodes','','Node expressions describe only the cited platform claim; they do not allocate revenue or shipments to a node.','',
               table(['Company','Platform','Source-native node','Device / process context','Review status','Source'],
                     [[p['entity_id'],p['name'],e['process_node'],e['process_node_context'],e['status'],source_link({'source_id':e['source_id'],'evidence':e},data)] for p,e in node_rows])]
    (out/'Atlas Coverage View.md').write_text('\n'.join(text)+'\n')
    return report
