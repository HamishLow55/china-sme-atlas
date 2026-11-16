"""Explicit CSV intake and a local evidence review page; never auto-integrates."""
import copy
import csv
import html
import json
from pathlib import Path
from .core import ROOT, load, read_json, write_json, require, validate, digest, valid_date

def allowed_inputs(*paths):
    from .library import _allowed
    require(all(_allowed(Path(p)) for p in paths),'Protected input or output path')

def import_csv(csv_path,mapping_path,output,root=ROOT):
    allowed_inputs(csv_path,mapping_path,output)
    mapping=read_json(mapping_path);data=load(root);rows=[]
    require(mapping.get('template') and mapping.get('columns'),'CSV intake needs a template and explicit column mapping')
    require(not Path(output).exists(),'Output exists; use a new proposal filename')
    require(Path(output).resolve().is_relative_to((root/'local').resolve()),'Intake output must be local, not canonical data')
    with Path(csv_path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        require(set(mapping['columns'].values())<=set(reader.fieldnames or []),'CSV header does not match mapping')
        for n,row in enumerate(reader,2):
            o=copy.deepcopy(mapping['template'])
            for target,column in mapping['columns'].items():
                parts=target.split('.');obj=o
                for part in parts[:-1]:obj=obj.setdefault(part,{})
                obj[parts[-1]]=row[column].strip()
            o.setdefault('evidence',{}).update(status='pending',reviewer='',review_date='')
            o['intake']={'csv_sha256':digest(csv_path),'mapping_sha256':digest(mapping_path),'csv_line':n}
            require(o['observation_id'] not in data['observations'],'Duplicate intake observation ID')
            data['observations'][o['observation_id']]=o;rows.append(o)
    require(rows,'CSV contains no observations');validate(data)
    write_json(output,rows)
    return {'proposal':str(output),'rows':len(rows),'status':'pending_review','integrated':False,
            'note':'No inferred units, magnitude conversions or automatic source verification.'}

def review_page(batch,root=ROOT):
    allowed_inputs(batch,root/'local/reviews')
    rows=read_json(batch);require(isinstance(rows,list) and rows,'Expected observation array')
    ids=[o['observation_id'] for o in rows];require(len(ids)==len(set(ids)),'Duplicate observation ID')
    paths=read_json(root/'local/source_paths.json') if (root/'local/source_paths.json').exists() else {}
    from .library import _allowed
    sources=load(root)['sources']
    esc=lambda s:html.escape(str(s),quote=True)
    cards=[]
    for i,o in enumerate(rows):
        e=o['evidence'];path=paths.get(o['source_id']);url=''
        if path and _allowed(Path(path)) and Path(path).is_file() and o['source_id'] in sources and digest(path)==sources[o['source_id']]['sha256']:
            url=Path(path).resolve().as_uri()+'#page='+str(e['page'])
        link=f'<a href="{esc(url)}" target="_blank" rel="noopener">Open original page {esc(e["page"])}</a>' if url else 'Original unresolved; resolve source before accepting.'
        detail={k:o.get(k) for k in ('entity_id','category_id','reporting_scope_id','platform_id','metric_id','value','relation','unit','period','dimensions','notes')}
        cards.append(f'<article><h2>{esc(o["observation_id"])}</h2><div class="pair"><section><pre>{esc(json.dumps(detail,ensure_ascii=False,indent=2))}</pre></section><section><p>{esc(o["source_id"])} · {link}</p><blockquote>{esc(e.get("excerpt",""))}</blockquote><p>Original label: {esc(e.get("original_label",""))}</p><label>Decision <select id="d{i}"><option>hold</option><option>accept</option><option>correct</option></select></label><p><textarea id="n{i}" placeholder="Original checked, correction or reason for hold"></textarea></p></section></div></article>')
    payload=json.dumps({'batch_sha256':digest(batch),'observation_ids':ids},ensure_ascii=True).replace('<','\\u003c')
    page='''<!doctype html><meta charset="utf-8"><title>Atlas evidence review</title>
<style>body{font:16px system-ui;max-width:1250px;margin:32px auto;padding:0 20px;color:#17252a}article{border-top:1px solid #bbb;padding:16px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}pre{white-space:pre-wrap;font-size:13px;background:#f1f4f5;padding:16px}blockquote{margin:0;padding:16px;background:#eef6ee;white-space:pre-wrap}textarea{width:95%;min-height:90px}button{padding:10px} @media(max-width:700px){.pair{grid-template-columns:1fr}}</style>
<h1>Atlas evidence review</h1><p>Compare the recorded scope and value with the original passage. The excerpt is a navigation aid: open the original before accepting. Decisions download locally and do not change canonical data.</p>
<label>Reviewer <input id="reviewer"></label> <button onclick="downloadReview()">Download decisions</button>'''+''.join(cards)+'''<script>
const batch='''+payload+''';
function downloadReview(){const reviewer=document.getElementById('reviewer').value.trim();if(!reviewer){alert('Enter reviewer identity');return;}
const decisions=batch.observation_ids.map((id,i)=>({observation_id:id,decision:document.getElementById('d'+i).value,notes:document.getElementById('n'+i).value}));
const result={batch_sha256:batch.batch_sha256,reviewer,review_date:new Date().toISOString().slice(0,10),decisions};
const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='review_decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
</script>'''
    out=root/'local/reviews'/('review_'+digest(batch)[:12]+'.html');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(page)
    return {'review_page':str(out),'observations':len(rows),'batch_sha256':digest(batch),'integrated':False}

def check_review(batch,decisions,corrected_batch=None):
    allowed_inputs(batch,decisions,*([corrected_batch] if corrected_batch is not None else []))
    rows=read_json(batch);review=read_json(decisions)
    require(isinstance(rows,list) and rows,'Expected observation array')
    require(all(isinstance(o,dict) and isinstance(o.get('observation_id'),str) and o['observation_id'] for o in rows),'Invalid candidate observation')
    require(len({o['observation_id'] for o in rows})==len(rows),'Duplicate candidate observation ID')
    require(review['batch_sha256']==digest(batch),'Review belongs to a different candidate batch')
    require(review.get('reviewer') and review.get('review_date'),'Review identity/date missing')
    valid_date(review['review_date'])
    expected={o['observation_id'] for o in rows};seen=set()
    for d in review['decisions']:
        require(d['observation_id'] in expected-seen,'Unknown or duplicate review decision')
        seen.add(d['observation_id']);require(d['decision'] in {'accept','correct','hold'},'Invalid review decision')
        require(d.get('notes','').strip(),'Every decision needs evidence notes')
    require(seen==expected,'Incomplete review')
    result={'status':'complete_review_record','decisions':len(seen),'integrated':False,'note':'Integrator must apply corrections and validate; this command never promotes observations.'}
    if corrected_batch is not None:
        corrected=read_json(corrected_batch)
        require(isinstance(corrected,list),'Expected corrected observation array')
        require(all(isinstance(o,dict) and isinstance(o.get('observation_id'),str) and o['observation_id'] for o in corrected),'Invalid corrected observation')
        actual={o['observation_id']:o for o in corrected}
        require(len(actual)==len(corrected),'Duplicate corrected observation ID')
        candidates={o['observation_id']:o for o in rows};replayed={}
        for decision in review['decisions']:
            if decision['decision']=='hold':continue
            oid=decision['observation_id'];row=copy.deepcopy(candidates[oid])
            patches=decision.get('corrections',[])
            require(isinstance(patches,list),'Corrections must be an array')
            require(bool(patches)==(decision['decision']=='correct'),'Correct decisions need patches; accept decisions must not include patches')
            for patch in patches:
                require(isinstance(patch,dict) and isinstance(patch.get('field'),str) and 'value' in patch,'Invalid correction patch')
                parts=patch['field'].split('.')
                require(all(parts) and parts[0]!='observation_id','Invalid correction field or observation identity change')
                target=row
                for part in parts[:-1]:
                    require(isinstance(target,dict) and isinstance(target.get(part),dict),'Correction path does not identify an object')
                    target=target[part]
                target[parts[-1]]=copy.deepcopy(patch['value'])
            replayed[oid]=row
        require(set(actual)==set(replayed),'Corrected staging must contain exactly the non-held observations')
        for oid,row in replayed.items():
            require(row==actual[oid],f'Corrected staging differs from review patch replay: {oid}')
        result.update(replay='exact_match',corrected_observations=len(actual),corrected_batch_sha256=digest(corrected_batch))
    return result
