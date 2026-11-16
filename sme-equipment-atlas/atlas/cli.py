import argparse
import collections
from contextlib import closing
from collections import Counter
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from .core import ROOT, ValidationError, build, digest, load, read_json, require, snapshot, validate, validate_observation, verify_assets, write_json

def discover(workspace,vault,tracker):
    """Bounded, local-only catalogue; explicit roots avoid protected content."""
    require(workspace.is_dir() and vault.is_dir(),'Workspace/vault missing')
    sources=load()['sources']; by_hash={s['sha256']:s['source_id'] for s in sources.values()}
    files=set()
    from .library import _files, _allowed
    for folder in (workspace/'Financial reports',workspace/'Assorted sources'):
        for p in _files([folder])[0]:
            if p.is_file() and p.suffix.lower() in {'.pdf','.md','.csv'} and re.search('amec|naura|china[+_]micro|中微|北方华创',str(p),re.I):files.add(p)
    for folder in [vault/'CC docs/1 Primary sources/China SME sources/AMEC reports',vault/'CC docs/1 Primary sources/China SME sources/NAURA reports',vault/'CC docs/2 Analysis/Etch & HAR']:
        for p in _files([folder])[0]:
            if p.is_file() and p.suffix.lower() in {'.pdf','.md','.csv'}:files.add(p)
    p=vault/'CC docs/2 Analysis/SME Accuracy Study/SME_Accuracy/AMEC_Etch_Equipment_Milestones.md'
    if p.exists():files.add(p)
    local=ROOT/'local';local.mkdir(exist_ok=True)
    db=sqlite3.connect(local/'catalog.sqlite');db.execute('DROP TABLE IF EXISTS documents')
    db.execute('CREATE TABLE documents (path TEXT PRIMARY KEY, sha256 TEXT, source_id TEXT, company TEXT, text TEXT)')
    records=[];resolved={}
    for p in sorted(files):
        # Do not follow links that would escape the explicitly allowed roots.
        real=p.resolve()
        require(not any(x in real.parts for x in ['Semis notes','_Unsourced (do not cite)']), 'Protected path encountered')
        sha=digest(p);sid=by_hash.get(sha,'')
        if p.suffix.lower()=='.pdf':
            try:text=subprocess.check_output(['pdftotext','-layout',str(p),'-'],text=True,stderr=subprocess.DEVNULL,timeout=30)
            except (subprocess.SubprocessError,FileNotFoundError):text=''
        else:text=p.read_text(encoding='utf-8-sig',errors='replace')
        company='amec' if re.search('amec|china[+_]micro|中微',str(p),re.I) else 'naura' if re.search('naura|北方华创',str(p),re.I) else 'mixed'
        db.execute('INSERT INTO documents VALUES (?,?,?,?,?)',(str(p),sha,sid,company,text))
        records.append({'path':str(p),'sha256':sha,'source_id':sid,'company':company,'text_extracted':bool(text)})
        if sid:resolved.setdefault(sid,str(p))
    db.commit();db.close()
    rows=[]
    require(_allowed(tracker),'Protected tracker path')
    if tracker.exists():
        conn=sqlite3.connect(tracker.resolve().as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
        for r in conn.execute("SELECT entity_id,title,published,pdf_url,downloaded,local_path FROM filings WHERE entity_id IN ('amec','naura')"):
            entry=dict(r);entry['tracked_path_exists']=bool(r['local_path'] and Path(r['local_path']).is_file());rows.append(entry)
        conn.close()
    # Preserve manually resolved sources if still valid. No tracker writes.
    paths=read_json(local/'source_paths.json') if (local/'source_paths.json').exists() else {}
    for sid,p in resolved.items():
        if sid not in paths or not Path(paths[sid]).is_file():paths[sid]=p
    write_json(local/'source_paths.json',paths)
    write_json(local/'source_catalog.json',records);write_json(local/'tracker_inventory.json',rows)
    report={'catalogued_locations':len(records),'unique_content_hashes':len({r['sha256'] for r in records}),'curated_sources_resolved':len(resolved),'tracker_records':len(rows),'tracker_existing_paths':sum(r['tracked_path_exists'] for r in rows),'scope':'AMEC/NAURA named local archives; their vault extracts; Etch & HAR; AMEC milestone note. Not a vault-wide inventory.','warning':'Tracker missing path/download flag does not establish local absence.'}
    write_json(local/'discovery_report.json',report)
    return report

def search(query,limit):
    p=ROOT/'local/catalog.sqlite';require(p.exists(),'Run discover first')
    words=query.lower().split();require(words,'Empty query')
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    conditions=['(lower(company || " " || path || " " || text) LIKE ?)' for _ in words]
    rows=db.execute('SELECT * FROM documents WHERE '+' AND '.join(conditions)+' LIMIT ?',tuple('%'+w+'%' for w in words)+(limit,)).fetchall()
    result=[]
    for r in rows:
        text=r['text']; needles=[w for w in words if w not in {'amec','naura'}];i=text.lower().find(needles[-1]) if needles else 0
        result.append({'path':r['path'],'source_id':r['source_id'],'sha256':r['sha256'],'snippet':text[max(0,i-100):max(0,i)+350].strip()})
    db.close();return result

def publish(vault,apply=False):
    raise ValidationError('Vault publishing is retired; use canonical repository evidence.')
    from .library import _allowed
    require(_allowed(vault),'Protected vault path')
    build();files={
        ROOT/'build/Atlas Data View.md':vault/'CC docs/2 Analysis/SME Equipment Atlas/Atlas Data View.md',
        ROOT/'build/series.csv':vault/'CC docs/2 Analysis/SME Equipment Atlas/atlas_series_v2.csv',
        ROOT/'build/all_observations.csv':vault/'CC docs/2 Analysis/SME Equipment Atlas/atlas_all_observations.csv',
        ROOT/'build/Atlas Coverage View.md':vault/'CC docs/2 Analysis/SME Equipment Atlas/Atlas Coverage View.md',
        ROOT/'build/Atlas Reconciliation View.md':vault/'CC docs/3 Working research (speculative)/SME Equipment Atlas/Atlas Reconciliation View.md',
        ROOT/'build/run_manifest.json':vault/'CC docs/3 Working research (speculative)/SME Equipment Atlas/atlas_run_manifest.json',
    }
    # Raw canonical observations are exported to Tier 1, not edited in the vault.
    write_json(ROOT/'build/atlas_observations_v2.json',list(load()['observations'].values()))
    files[ROOT/'build/atlas_observations_v2.json']=vault/'CC docs/1 Primary sources/Market & revenue data/SME Equipment Atlas/atlas_observations_v2.json'
    home=vault/'CC docs/2 Analysis/SME Equipment Atlas/Equipment Atlas.md'
    require(all(_allowed(p) and p.resolve().is_relative_to(vault.resolve()) for p in [home,*files.values()]),'Publishing destination escapes vault or targets protected content')
    body='# Equipment Atlas\n\nStart here for the second pilot. Structured evidence is versioned in [the GitHub repository](https://github.com/HamishLow55/china-sme-atlas); this page is yours to edit and is never overwritten.\n\n![[Atlas Data View]]\n\n## Reconciliation and Models\n\n[[Atlas Reconciliation View]] separates derived estimates and unresolved market-share work from source observations.\n\n## Working Notes\n\nAdd interpretation, questions and drafting here.\n\n## Updating\n\nSee the repository README for local discovery, validation, proposed evidence batches, snapshots and publishing. The original [[Etching Pilot]] remains a historical pilot; its CSVs and refresh script are no longer the current dataset.\n'
    if apply:
        require(vault.is_dir(),'Vault missing')
        for src,dst in files.items():
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        # Machine-specific original links belong only in the local vault export.
        paths_file=ROOT/'local/source_paths.json'
        if paths_file.exists():
            from .library import _allowed
            sources=load()['sources'];verified={sid:path for sid,path in read_json(paths_file).items() if sid in sources and _allowed(Path(path)) and Path(path).is_file() and digest(path)==sources[sid]['sha256']}
            for filename in ['Atlas Data View.md','Atlas Coverage View.md']:
                target=vault/'CC docs/2 Analysis/SME Equipment Atlas'/filename
                rendered=target.read_text(encoding='utf-8')
                for sid,path in verified.items():
                    rendered=rendered.replace(f'(local source: `{sid}`)',f'([local original]({Path(path).resolve().as_uri()}))')
                target.write_text(rendered,encoding='utf-8')
        if not home.exists():home.write_text(body,encoding='utf-8')
    return {'apply':apply,'generated_targets':[str(p) for p in files.values()],'human_page_created_only_if_absent':str(home)}

def check_batch(path, registries=None, metric_decisions=None):
    from .intake import allowed_inputs
    allowed_inputs(path)
    data=load();rows=read_json(path)
    decisions={}
    if metric_decisions is not None:
        allowed_inputs(metric_decisions)
        decisions=read_json(metric_decisions)
        require(isinstance(decisions,dict),'Metric decisions must map metric IDs to reuse reviews')
    if registries is not None:
        allowed_inputs(registries)
        additions=read_json(registries)
        tables={'datasets':('datasets','dataset_id'),'sources':('sources','source_id'),
                'entities':('entities','entity_id'),'reporting_scopes':('scopes','reporting_scope_id'),
                'metrics':('metrics','metric_id'),'categories':('categories','category_id'),
                'platforms':('platforms','platform_id')}
        require(isinstance(additions,dict),'Proposed registries must be an object')
        for section,records in additions.items():
            require(section in tables,f'Unknown proposed registry: {section}')
            require(isinstance(records,list),f'{section}: expected array')
            table,key=tables[section];seen=set()
            for record in records:
                require(isinstance(record,dict) and isinstance(record.get(key),str) and record[key],
                        f'{section}: record needs a nonempty {key}')
                rid=record[key]
                require(rid not in seen,f'Duplicate proposed registry ID: {rid}');seen.add(rid)
                require(rid not in data[table] or data[table][rid]==record,
                        f'{rid}: proposed registry would replace an existing definition; review separately')
                if section=='metrics' and rid not in data['metrics']:
                    from .metric_review import validate_metric_proposal
                    validate_metric_proposal(record,data['metrics'],decisions.get(rid))
                data[table][rid]=record
    require(isinstance(rows,list) and rows,'Batch must be a nonempty observation array')
    errors=[];valid_rows=[]
    for position,o in enumerate(rows,1):
        if not isinstance(o,dict) or not isinstance(o.get('observation_id'),str) or not o['observation_id']:
            errors.append(f'Row {position}: needs a nonempty observation_id');continue
        if o['observation_id'] in data['observations']:
            errors.append(f"{o['observation_id']}: batch ID already exists");continue
        data['observations'][o['observation_id']]=o;valid_rows.append(o)
    for o in valid_rows:
        try:validate_observation(o,data)
        except (ValidationError,KeyError,ValueError) as exc:errors.append(f"{o['observation_id']}: {exc}")
    require(not errors,'Batch row errors: '+ '; '.join(errors))
    validate(data)
    return {'status':'valid_proposal','rows':len(rows),'integrated':False,'registries_staged':registries is not None,'note':'Actual atlas validation with optional in-memory registry additions. No files changed; independent source review is still required.'}

# Quantified operational wording, tolerant of year-to-year drift between filings.
GAP_TERMS={'stock':r'(?:累计装机|装机量|累计安装|累计出货|累计交付|累计付运|累计销售|累计供应|累计发货|累计流片)',
 'flow':r'(?:当年付运|全年付运|生产付运|年付运|新增装机|新增出货)',
 'orders':r'(?:在手订单|新增订单|累计订单|已签订单)'}
GAP_NUM=r'(?:[0-9][0-9,\.]{0,12}|[一二三四五六七八九十百千万]{1,6})'
GAP_UNIT=r'(?:个|台|套|腔|反应台|反应腔|条|家|万片|片|亿片|万元|亿元)'
GAP_CUST=r'(?:条[^，。；]{0,8}?(?:生产线|产线)|家[^，。；]{0,6}?客户|个客户|家晶圆厂)'

def coverage_gaps(limit=0):
    """Registered pages carrying a quantified operational clause that produced no observation.

    Locates candidates only. A hit is not evidence that a value is extractable, and a miss is not
    evidence of absence: it reports where the indexed text of a registered original has not been
    mined. Requires a built library index."""
    data=load();local=ROOT/'local'
    path=local/'library.sqlite'
    require(path.exists(),'Run library-index first')
    by_sha={s['sha256']:sid for sid,s in data['sources'].items() if s.get('sha256')}
    read={};known={}
    for o in data['observations'].values():
        read.setdefault(o['source_id'],set()).add(o['evidence']['page'])
        for v in (str(o.get('value','')),str(o.get('evidence',{}).get('reported_value',''))):
            v=v.replace(',','').rstrip('0').rstrip('.') if '.' in v else v.replace(',','')
            if v:known.setdefault(o['source_id'],set()).add(v)
    pats={k:re.compile(v+r'[^。；]{0,30}?'+GAP_NUM+r'\s*'+GAP_UNIT) for k,v in GAP_TERMS.items()}
    pats['customers']=re.compile(GAP_NUM+r'\s*'+GAP_CUST)
    rows=[]
    uri=path.resolve().as_uri()+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True)) as db:
        db.row_factory=sqlite3.Row
        for r in db.execute('select sha256,page,text from pages'):
            sid=by_sha.get(r['sha256'])
            if not sid or r['page'] in read.get(sid,()):continue
            text=re.sub(r'\s+','',r['text'] or '')
            kinds=[];quants=set()
            for k,pat in pats.items():
                m=pat.search(text)
                if not m:continue
                kinds.append(k);quants|={q.replace(',','') for q in re.findall(r'[0-9][0-9,\.]{1,12}',m.group(0))}
            if not kinds:continue
            # A restated claim on an unmined page is not an evidence gap: the value is already held
            # from elsewhere in the same original. Report it separately rather than as unmined.
            captured=quants and quants <= known.get(sid,set())
            rows.append({'source_id':sid,'page':r['page'],'signals':sorted(kinds),
                         'status':'restates_captured_value' if captured else 'unmined'})
    rows.sort(key=lambda x:(x['source_id'],x['page']))
    unmined=[x for x in rows if x['status']=='unmined']
    per=Counter(x['source_id'] for x in unmined)
    return {'unmined_candidate_pages':len(unmined),
            'restating_pages_excluded':len(rows)-len(unmined),
            'sources_affected':len(per),
            'by_source':dict(per.most_common()),
            'pages':(unmined[:limit] if limit else unmined),
            'limitation':'Indexed-text keyword locator over registered originals only. Not proof that a page holds an extractable value, and silence is not proof of absence.'}


def duplicates(limit=0):
    """Observations that encode one disclosure twice under different identifiers.

    Identifier uniqueness is already enforced; this finds the other kind, where two rows carry the
    same claim from the same page of the same source. Parallel extraction packets produce these
    routinely, and nothing else in the repository looks for them. A hit is not automatically a
    defect: a source may legitimately restate a figure, and an issuer's own restatement across
    vintages is distinguished by reporting_basis. Read the pair before dropping either."""
    data=load()
    groups=collections.defaultdict(list)
    for o in data['observations'].values():
        dims=o['dimensions']
        key=(o['entity_id'],o['metric_id'],o['unit'],o['value'],o['period']['end'],o['period']['kind'],
             o['source_id'],o['evidence']['page'],o['reporting_scope_id'],o.get('platform_id',''),
             o.get('reporting_basis',''),dims.get('counterparty_bucket',''),
             dims.get('reported_counterparty_name',''),dims.get('workforce_cohort',''),
             dims.get('geography',''),dims.get('cost_component',''))
        groups[key].append(o['observation_id'])
    obs=data['observations']
    dupes=[]
    for key,ids in groups.items():
        if len(ids)<2:continue
        ids=sorted(ids)
        # A group is resolved once every row but one declares coincident_value against a member of
        # the same group. That records which situation applies; it does not merge anything.
        declared={i:obs[i].get('coincident_value') for i in ids}
        bases={d['basis'] for d in declared.values() if d}
        undeclared=[i for i in ids if not declared[i]]
        targets_inside=all(d['counterpart_observation_id'] in ids for d in declared.values() if d)
        resolved=len(undeclared)==1 and targets_inside and len(bases)==1
        dupes.append({'observation_ids':ids,'entity_id':key[0],'metric_id':key[1],'value':key[3],
                      'unit':key[2],'period_end':key[4],'source_id':key[6],'page':key[7],
                      'status':'resolved' if resolved else 'unresolved',
                      'basis':sorted(bases)[0] if resolved else None})
    dupes.sort(key=lambda d:(d['status']!='unresolved',d['entity_id'],d['metric_id'],d['period_end']))
    unresolved=[d for d in dupes if d['status']=='unresolved']
    counts=collections.Counter(d['basis'] for d in dupes if d['status']=='resolved')
    # The key above includes reporting_scope_id, so it cannot see the more dangerous class: one figure
    # carried under two different scopes of the same filing. Within a scope a duplicate is usually a
    # harmless restatement; across scopes the rows are parallel partitions of one perimeter, and when
    # their category_ids differ an equipment rollup and a company rollup can each pick one up. The
    # schema's coincident_value contract is deliberately scope-blind (it requires only entity, metric,
    # unit, value, period and source to agree), so these are declarable and simply were not declared.
    wide=collections.defaultdict(list)
    for o in data['observations'].values():
        wide[(o['entity_id'],o['metric_id'],o['unit'],o['value'],o['period']['end'],o['source_id'])].append(o)
    cross=[]
    for key,rows in wide.items():
        if len(rows)<2 or len({r['reporting_scope_id'] for r in rows})<2:continue
        undecl=[r['observation_id'] for r in rows if not r.get('coincident_value')]
        cats=sorted({r['category_id'] for r in rows})
        cross.append({'observation_ids':sorted(r['observation_id'] for r in rows),
                      'entity_id':key[0],'metric_id':key[1],'value':key[3],'unit':key[2],
                      'period_end':key[4],'source_id':key[5],'category_ids':cats,
                      'scopes':sorted({r['reporting_scope_id'] for r in rows}),
                      'status':'resolved' if len(undecl)<=1 else 'undeclared',
                      'spans_categories':len(cats)>1})
    cross.sort(key=lambda d:(d['status']!='undeclared',not d['spans_categories'],d['entity_id'],d['metric_id']))
    cross_undecl=[d for d in cross if d['status']=='undeclared']
    return {'duplicate_groups':len(dupes),'unresolved_groups':len(unresolved),
            'observations_involved':sum(len(d['observation_ids']) for d in dupes),
            'resolved_by_basis':dict(counts),
            'groups':(unresolved or dupes)[:limit] if limit else (unresolved or dupes),
            'cross_scope_groups':len(cross),'cross_scope_undeclared':len(cross_undecl),
            'cross_scope_spanning_categories':sum(1 for d in cross_undecl if d['spans_categories']),
            'cross_scope':(cross_undecl or cross)[:limit] if limit else (cross_undecl or cross),
            'limitation':'Same claim, same source page, same scope and basis. A legitimate restatement across vintages differs in reporting_basis and is not reported here. Unresolved groups are listed first; a resolved group keeps both rows on disk and records in coincident_value whether an aggregation should count one or both. cross_scope reports the scope-blind class separately: one figure under two scopes of one filing, which this report could not see before and which is NOT automatically a defect -- an issuer whose revenue comes from one industry and one region prints the same total in its 分行业 and 分地区 tables legitimately. Those spanning more than one category_id are listed first, because that is where an equipment-level and a company-level rollup can each count the same money.'}


def main():
    parser=argparse.ArgumentParser(description='Local-first equipment evidence and reconciliation')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('validate');sub.add_parser('verify-assets')
    p=sub.add_parser('build');p.add_argument('--dependencies',action='store_true',help='Opt in to the conservative impact graph');p.add_argument('--views',action='store_true',help='Opt in to repository reading views')
    p=sub.add_parser('library-index');p.add_argument('paths',type=Path,nargs='*');p.add_argument('--manifest',type=Path)
    p=sub.add_parser('library-search');p.add_argument('query');p.add_argument('--limit',type=int,default=10)
    p=sub.add_parser('packet');p.add_argument('task_id')
    sub.add_parser('coverage');sub.add_parser('eval-retrieval')
    p=sub.add_parser('impact');p.add_argument('previous',type=Path)
    p=sub.add_parser('review');p.add_argument('batch',type=Path)
    p=sub.add_parser('check-review');p.add_argument('batch',type=Path);p.add_argument('decisions',type=Path);p.add_argument('--corrected-batch',type=Path)
    p=sub.add_parser('import-csv');p.add_argument('csv',type=Path);p.add_argument('mapping',type=Path);p.add_argument('output',type=Path)
    p=sub.add_parser('discover');p.add_argument('--workspace',type=Path,required=True);p.add_argument('--vault',type=Path,required=True);p.add_argument('--tracker',type=Path,required=True)
    p=sub.add_parser('search');p.add_argument('query');p.add_argument('--limit',type=int,default=10)
    p=sub.add_parser('check-batch');p.add_argument('file',type=Path);p.add_argument('--registries',type=Path);p.add_argument('--metric-decisions',type=Path)
    sub.add_parser('verify-aliases')
    p=sub.add_parser('check-pages');p.add_argument('batch',type=Path)
    p=sub.add_parser('check-native-pages');p.add_argument('batch',type=Path);p.add_argument('--source-id')
    p=sub.add_parser('coverage-gaps');p.add_argument('--limit',type=int,default=0)
    p=sub.add_parser('duplicates');p.add_argument('--limit',type=int,default=0)
    p=sub.add_parser('snapshot');p.add_argument('destination',type=Path)
    # Vault publishing retired by user directive; legacy function retained for history.
    sub.add_parser('statistics-build');sub.add_parser('statistics-check')
    args=parser.parse_args()
    try:
        if args.command=='validate':result=validate(load(),ROOT)
        elif args.command=='library-index':
            from .library import index_library, _allowed
            roots=list(args.paths)
            if args.manifest:
                require(_allowed(args.manifest),'Protected manifest')
                roots.extend(Path(p) for p in read_json(args.manifest))
            require(roots,'Supply explicit roots or --manifest')
            result=index_library(roots,ROOT/'local',load()['sources'])
            resolver=ROOT/'local/source_paths.json'
            paths=read_json(resolver) if resolver.exists() else {}
            sources=load()['sources']
            for row in result['records']:
                for sid in row['source_ids']:
                    p=Path(paths[sid]) if sid in paths else None
                    if not p or not _allowed(p) or not p.is_file() or digest(p)!=sources[sid]['sha256']:
                        paths[sid]=row['path']
            write_json(resolver,paths)
            write_json(ROOT/'local/library_report.json',result)
            result={k:v for k,v in result.items() if k not in {'records','excluded_paths'}}
        elif args.command=='library-search':
            from .library import search_library
            from .research import alias_map
            result=search_library(args.query,ROOT/'local',aliases=alias_map(load()),limit=args.limit)
        elif args.command=='packet':
            from .research import packet
            result=packet(args.task_id)
        elif args.command=='coverage':
            from .research import coverage
            result=coverage()
        elif args.command=='eval-retrieval':
            from .research import evaluate_retrieval
            result=evaluate_retrieval();print(json.dumps(result,ensure_ascii=False,indent=2))
            raise SystemExit(0 if result['passed']==result['total'] else 1)
        elif args.command=='impact':
            from .research import impact
            result=impact(args.previous)
        elif args.command=='review':
            from .intake import review_page
            result=review_page(args.batch)
        elif args.command=='check-review':
            from .intake import check_review
            result=check_review(args.batch,args.decisions,args.corrected_batch)
        elif args.command=='import-csv':
            from .intake import import_csv
            result=import_csv(args.csv,args.mapping,args.output)
        elif args.command=='build':
            m=build(dependencies=args.dependencies,views=args.views);result={'output':'build/','input_snapshot_sha256':m['input_snapshot_sha256'],'reconciliations':m['reconciliation_results']}
        elif args.command=='verify-aliases':
            from .aliases import verify_aliases
            report=verify_aliases();rows=report['aliases']
            counts={state:sum(r['status']==state for r in rows) for state in ['in_own_source','in_another_entity_source','unsourced']}
            by_kind={kind:{state:sum(r['status']==state and r['kind']==kind for r in rows)
                           for state in ['in_own_source','in_another_entity_source','unsourced']}
                     for kind in ('entity','platform')}
            result={'status':'pass' if not counts['unsourced'] else 'needs_attention','counts':counts,
                    'counts_by_kind':by_kind,
                    'unsourced':[r for r in rows if r['status']=='unsourced'],
                    'sources_without_text_layer':report['sources_without_text_layer'],
                    'note':'An alias found in no held source may still be a real name, but nothing in this repository evidences it. '
                           'A scanned filing returns no text, so an alias printed only there reads as unsourced here: check the '
                           'listed sources before treating an absence as a fabrication.',
                    'platform_alias_caveat':'The unsourced platform count is NOT a fabrication count, and should not be read as one. '
                           'Most unsourced platform aliases in this atlas are labels the atlas constructed rather than strings an '
                           'issuer printed: an English rendering of a Chinese product name, a company name prefixed to a product '
                           'type, or an internal annotation such as a bracketed source-described-family marker. Those are a '
                           'convention question about what the aliases field is for. An invented product identifier is the actual '
                           'defect class -- one has been found, a model number on a platform whose issuer never printed it -- and '
                           'it hides in this population, so the list needs reading rather than counting.'}
            print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['status']=='pass' else 1)
        elif args.command=='verify-assets':
            result=verify_assets();print(json.dumps(result,indent=2));raise SystemExit(0 if all(r['status']=='verified' for r in result) else 1)
        elif args.command=='discover':result=discover(args.workspace,args.vault,args.tracker)
        elif args.command=='search':result=search(args.query,args.limit)
        elif args.command=='check-batch':result=check_batch(args.file,args.registries,args.metric_decisions)
        elif args.command in {'check-pages','check-native-pages'}:
            from .intake import allowed_inputs
            from .pagecheck import preflight,native_rows
            resolver=ROOT/'local/source_paths.json'
            allowed_inputs(args.batch,resolver)
            rows=read_json(args.batch)
            if args.command=='check-native-pages':rows=native_rows(rows,args.source_id)
            require(isinstance(rows,list) and rows and all(isinstance(r,dict) for r in rows),'Expected a nonempty observation array')
            checks=preflight(rows,load(),read_json(resolver) if resolver.exists() else {})
            counts={status:sum(r['status']==status for r in checks) for status in ['pass','mismatch','unavailable']}
            result={'status':'pass' if counts['pass']==len(rows) else 'needs_attention','counts':counts,'checks':checks,'note':'Native numeric tokens on a hash-verified physical page; not row/column interpretation or source review. No evidence status changed.'}
            print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['status']=='pass' else 1)
        elif args.command=='coverage-gaps':result=coverage_gaps(args.limit)
        elif args.command=='duplicates':result=duplicates(args.limit)
        elif args.command=='snapshot':result={'snapshot':str(snapshot(ROOT,args.destination))}
        elif args.command=='statistics-build':
            from .statistics import build_china_customs
            result=build_china_customs()
        elif args.command=='statistics-check':
            from .statistics import check_statistics
            result=check_statistics()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValidationError,KeyError,ValueError,FileNotFoundError) as exc:
        parser.exit(1,'Validation failed: '+str(exc)+'\n')
