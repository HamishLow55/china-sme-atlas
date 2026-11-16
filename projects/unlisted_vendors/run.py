"""Validate and aggregate bottom-up estimates for vendors without regular filings (see README.md).

Each firm has estimates/<firm>.csv and sources/<firm>.csv. This run checks them
against docs/estimation_standards.md, sums them by equipment group, and compares the front-end total
with CEPEA's front-end revenue minus Atlas-covered vendors. The comparison is a cross-check, not a target.
"""
import json
from pathlib import Path
import pandas as pd
from sme_analysis import manifest, reference
from sme_analysis.cli import project_module

HERE = Path(__file__).resolve().parent
EST_COLS = ['firm_id','unit','group_id','year','revenue_cny_m_low','revenue_cny_m_base','revenue_cny_m_high','geography','scope_note',
            'method_tier','method','narrow_range_reason','evidence_ids','overlaps','status','author','as_of']
SRC_COLS = ['evidence_id','title','publisher','url','published','accessed','trust_tier','locator','note']
# Minimum range around base per method tier (standards section 2): (low factor, high factor).
TIER_RANGE = {'A':(1.0,1.0),'B':(0.85,1.15),'C':(0.70,1.30),'D':(0.60,1.60),'E':(0.50,2.00)}
WFE_GROUPS = ['litho','deposition','dry_etch','process_control','cleaning_strip','cmp','doping','thermal','track_automation_other']

def validate_firm(est_path, src_path, groups, notes_dir=None):
    problems=[];firm=est_path.stem;notes_dir=Path(notes_dir) if notes_dir else HERE/'notes'
    if not src_path.is_file():return None,[f'{firm}: missing sources/{firm}.csv']
    e=pd.read_csv(est_path,dtype=str,keep_default_na=False);s=pd.read_csv(src_path,dtype=str,keep_default_na=False)
    for name,df,cols in (('estimates',e,EST_COLS),('sources',s,SRC_COLS)):
        missing=[c for c in cols if c not in df.columns]
        if missing:problems.append(f'{firm} {name}: missing columns {missing}')
    if problems:return None,problems
    if s['evidence_id'].duplicated().any():problems.append(f'{firm} sources: duplicate evidence_id')
    bad_src=s[~s['trust_tier'].isin(['1','2','3','4'])|~s['url'].str.startswith('http')]
    for _,r in bad_src.iterrows():problems.append(f'{firm} sources {r["evidence_id"]}: needs trust_tier 1-4 and a full URL')
    ids=set(s['evidence_id']);tiers=dict(zip(s['evidence_id'],s['trust_tier']))
    for i,r in e.iterrows():
        at=f'{firm} row {i+2}'
        if r['firm_id']!=firm:problems.append(f'{at}: firm_id must be {firm}')
        if r['group_id'] not in groups:problems.append(f'{at}: unknown group_id {r["group_id"]}')
        if r['method_tier'] not in TIER_RANGE:problems.append(f'{at}: method_tier must be A-E');continue
        if r['status'] not in ('proposed','reviewed'):problems.append(f'{at}: status must be proposed or reviewed')
        if r['geography'] not in ('china','global','unknown'):problems.append(f'{at}: geography must be china/global/unknown')
        try:lo,ba,hi=(float(r[c]) for c in ('revenue_cny_m_low','revenue_cny_m_base','revenue_cny_m_high'));year=int(r['year'])
        except ValueError:problems.append(f'{at}: year and revenue columns must be numeric');continue
        if not lo<=ba<=hi:problems.append(f'{at}: need low <= base <= high')
        flo,fhi=TIER_RANGE[r['method_tier']]
        if ba>0 and (lo>ba*flo+1e-9 or hi<ba*fhi-1e-9) and not r['narrow_range_reason'].strip():
            problems.append(f'{at}: range narrower than tier {r["method_tier"]} default ({flo:g}x-{fhi:g}x) without narrow_range_reason')
        ev=[x for x in r['evidence_ids'].split(';') if x.strip()]
        if not ev:problems.append(f'{at}: evidence_ids required')
        unknown=[x for x in ev if x not in ids]
        if unknown:problems.append(f'{at}: evidence_ids not in sources: {unknown}')
        if ev and r['method_tier'] in ('A','B','C') and all(tiers.get(x,'4') in ('3','4') for x in ev):
            problems.append(f'{at}: tier {r["method_tier"]} needs at least one trust-tier 1-2 source')
    return e,problems

def run(atlas, out, preview=None):
    groups=set(reference.load('segments')['group_id'])
    frames=[];problems={}
    for p in sorted((HERE/'estimates').glob('*.csv')):
        e,probs=validate_firm(p,HERE/'sources'/f'{p.stem}.csv',groups)
        problems[p.stem]=probs
        if e is not None and not probs:frames.append(e)
    (out/'validation.json').write_text(json.dumps(problems,indent=2,ensure_ascii=False)+'\n')
    cols=['revenue_cny_m_low','revenue_cny_m_base','revenue_cny_m_high']
    est=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=EST_COLS)
    for c in cols:est[c]=pd.to_numeric(est[c])
    est['year']=pd.to_numeric(est['year'])
    est.to_csv(out/'estimates_all.csv',index=False)
    by=est.groupby(['group_id','year'])[cols].sum().reset_index() if len(est) else pd.DataFrame(columns=['group_id','year']+cols)
    by.to_csv(out/'by_group.csv',index=False)
    # Cross-check: CEPEA front-end revenue minus Atlas-covered vendors vs estimated front-end revenue (USD m).
    share=project_module('china_share_by_segment');fx=share.fx_cny_per_usd(atlas)
    # Same overlap rules as the segment project: drop rows the Atlas numerator now covers, and global rows.
    dom,_=share.domestic_by_vendor(atlas,fx);cepea=share.cepea_frontend(atlas,fx);layer=share.estimate_layer(dom,fx);rows=[]
    for y in share.YEARS:
        covered=dom[(dom['year']==y)&dom['group_id'].isin(WFE_GROUPS)&dom['in_share']]['value_usd'].sum()/1e6
        fe=layer[(layer['year']==y)&layer['group_id'].isin(WFE_GROUPS)&(layer['dropped']=='')]
        rows.append({'year':y,'cepea_frontend_usd_m':cepea.get(y,float('nan'))/1e6,'atlas_covered_usd_m':covered,
                     'cepea_residual_usd_m':cepea.get(y,float('nan'))/1e6-covered,
                     **{f'unlisted_estimate_usd_m_{c}':fe[f'usd_{c}'].sum()/1e6 for c in ('low','base','high')},'firms':'; '.join(sorted(set(fe['firm_id'])))})
    chk=pd.DataFrame(rows);chk.to_csv(out/'cepea_crosscheck.csv',index=False,float_format='%.1f')
    firms=sorted(problems);ok=[f for f in firms if not problems[f]]
    m=lambda v:f'{v:,.0f}'
    lines=['# Unlisted Vendor Estimates','',
        f'> Tier 3, generated by `sme-atlas-analysis` project `unlisted_vendors` against Atlas `{atlas.state["commit"][:7]}`. Bottom-up estimates under `docs/estimation_standards.md`. Proposed until reviewed.','',
        f'Firms with valid estimates: {", ".join(ok) if ok else "none yet"}. Firms with problems: {", ".join(f for f in firms if problems[f]) or "none"}.','',
        '## CEPEA cross-check (USD m; information, not a target)','',
        '| year | CEPEA front-end | Atlas-covered | CEPEA residual | unlisted estimate (low / base / high) | firms |','|---|---|---|---|---|---|']
    for r in chk.itertuples():
        lines.append(f'| {r.year} | {m(r.cepea_frontend_usd_m)} | {m(r.atlas_covered_usd_m)} | {m(r.cepea_residual_usd_m)} | {m(r.unlisted_estimate_usd_m_low)} / {m(r.unlisted_estimate_usd_m_base)} / {m(r.unlisted_estimate_usd_m_high)} | {r.firms} |')
    lines+=['','Estimates exclude rows for firms the Atlas numerator now covers (e.g. long-tail firms added in Atlas PR #101) and rows with `geography: global`. Atlas-covered revenue excludes held-out AMHS.','','CEPEA\'s survey may exclude non-reporting or loss-making firms, and Atlas-covered revenue mixes floors and all-geography figures. A mismatch here is information about coverage and definitions, not an error to close.']
    lines+=['','**Reading the 2024 row.** Yitang appears to be missing from CEPEA\'s first-reported 2024 sample, which explains part of the negative residual. CEPEA later restated the 2024 total upward by ¥6.2bn (¥124.1bn; front end about ¥55.5bn implied). CEPEA\'s front-end total is about 91–101% platforms, so the residual should not be read as the long tail.']
    (out/'summary.md').write_text('\n'.join(lines)+'\n')
    manifest.write(out,'unlisted_vendors',[atlas],['A-FX-CNY-USD'],'Bottom-up estimates; CEPEA comparison is a cross-check only.')
    return {'firms':firms,'valid':ok,'problems':{f:len(p) for f,p in problems.items()},'rows':len(est)}
