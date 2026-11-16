"""Judgement tables in reference/: segment definitions, customs mapping, assumptions, HBM stack, vendors.

These are research judgements, not data. Each row carries a status (`proposed` until
the author reviews it, then `reviewed`) and a basis/source. Validation keeps them consistent
with the pinned Atlas taxonomy.
"""
from pathlib import Path
import pandas as pd
from .data import ROOT

REF = ROOT/'reference'
REQUIRED = {
    'segments':['segment_id','name','group_id','wfe','atlas_categories','definition','status','source'],
    'customs_segment_map':['hs8','origin_rule','group_id','allocation','basis','status'],
    'assumptions':['assumption_id','description','value','low','high','unit','basis','source','status'],
    'vendors':['entity_id','name','include','parent_note','status','source'],
    'scope_group_map':['reporting_scope_id','group_id','basis','status','source'],
    'hbm_tool_stack':['step_id','hbm_stage','tool_family','atlas_categories','group_id','customs_codes','domestic_candidates','foreign_incumbents','status','source'],
    'product_splits':['split_id','entity_id','reporting_scope_id','year','group_id','share_low','share_base','share_high','method_tier','basis','source','status'],
    'geography_splits':['entity_id','year','china_share_low','china_share_base','china_share_high','method_tier','basis','source','status'],
    'hbm_step_market_map':['step_id','market_basis','group_id','import_hs8','domestic_entities','note','status','source'],
}
STATUSES = {'proposed','reviewed'}

def load(name):
    return pd.read_csv(REF/f'{name}.csv',dtype=str,keep_default_na=False)

def assumption(aid):
    row=load('assumptions').set_index('assumption_id').loc[aid]
    f=lambda x:float(x) if x not in ('',None) else None
    return {'id':aid,'value':f(row['value']),'low':f(row['low']),'high':f(row['high']),'unit':row['unit'],'status':row['status']}

def validate(atlas=None):
    """Structural checks; with an Atlas, also check category ids against its taxonomy."""
    problems=[]
    tables={n:load(n) for n in REQUIRED}
    for n,cols in REQUIRED.items():
        t=tables[n];missing=[c for c in cols if c not in t.columns]
        if missing:problems.append(f'{n}: missing columns {missing}');continue
        bad=t[~t['status'].isin(STATUSES)]
        if len(bad):problems.append(f'{n}: invalid status in {len(bad)} rows')
        key=t.columns[0]
        if t[key].duplicated().any() and n not in ('customs_segment_map','geography_splits'):problems.append(f'{n}: duplicate {key}')
    groups=set(tables['segments']['group_id'])
    for n in ('customs_segment_map','hbm_tool_stack','scope_group_map','product_splits','hbm_step_market_map'):
        unknown=set(tables[n]['group_id'])-groups
        if unknown:problems.append(f'{n}: unknown group_id {sorted(unknown)}')
    ps=tables['product_splits']
    if len(ps) and not problems:
        v=ps[['share_low','share_base','share_high']].astype(float)
        if ((v['share_low']>v['share_base']+1e-9)|(v['share_base']>v['share_high']+1e-9)|(v.min(axis=1)<0)|(v.max(axis=1)>1)).any():
            problems.append('product_splits: shares must satisfy 0 <= low <= base <= high <= 1')
        for key,grp in ps.assign(**v).groupby(['entity_id','reporting_scope_id','year']):
            for c in ('share_low','share_base'):
                if grp[c].sum()>1+1e-9:problems.append(f'product_splits: {c} sums above 1 for {key}')
        if ps[['entity_id','year','group_id']].duplicated().any():problems.append('product_splits: one row per entity, year and group')
    gs=tables['geography_splits']
    if gs[['entity_id','year']].duplicated().any():problems.append('geography_splits: one row per entity and year')
    if len(gs):
        v=gs[['china_share_low','china_share_base','china_share_high']].astype(float)
        if ((v.iloc[:,0]>v.iloc[:,1]+1e-9)|(v.iloc[:,1]>v.iloc[:,2]+1e-9)|(v.min(axis=1)<0)|(v.max(axis=1)>1)).any():
            problems.append('geography_splits: shares must satisfy 0 <= low <= base <= high <= 1')
    steps=set(tables['hbm_tool_stack']['step_id'])
    for n in ('hbm_step_market_map',):
        if set(tables[n]['step_id'])!=steps:problems.append(f'{n}: must have exactly one row per hbm_tool_stack step')
    if not tables['hbm_step_market_map']['market_basis'].isin({'group','pool','none'}).all():problems.append('hbm_step_market_map: market_basis must be group, pool or none')
    sg=tables['scope_group_map']
    if 'in_share' in sg.columns and not sg['in_share'].isin({'yes','no','exclude'}).all():problems.append('scope_group_map: in_share must be yes, no or exclude')
    a=tables['assumptions']
    if (a['basis'].str.strip()=='').any():problems.append('assumptions: every row needs a basis')
    for _,r in tables['customs_segment_map'].iterrows():
        kind,_,ref=r['allocation'].partition(':')
        if kind not in ('full','amount_usd','share','residual','excluded'):problems.append(f'customs_segment_map {r["hs8"]}: unknown allocation {kind}')
        if kind in ('amount_usd','share') and ref not in set(a['assumption_id']):problems.append(f'customs_segment_map {r["hs8"]}: unknown assumption {ref}')
    if atlas is not None:
        cats={c['category_id'] for c in atlas.registries['categories']}
        ents={e['entity_id'] for e in atlas.registries['entities']}
        for n in ('segments','hbm_tool_stack'):
            for v in tables[n]['atlas_categories']:
                for c in filter(None,v.split(';')):
                    if c not in cats:problems.append(f'{n}: category {c} not in Atlas taxonomy')
        for e in tables['vendors']['entity_id']:
            if e not in ents:problems.append(f'vendors: {e} not an Atlas entity at {atlas.state["commit"][:7]}')
        scopes={o.get('reporting_scope_id','') for o in atlas.registries['observations']}
        for n in ('product_splits','geography_splits'):
            for e in set(tables[n]['entity_id'])-ents:problems.append(f'{n}: {e} not an Atlas entity')
        for sc in set(tables['product_splits']['reporting_scope_id'])-scopes:problems.append(f'product_splits: {sc} has no observations')
        for sc in tables['scope_group_map']['reporting_scope_id']:
            if sc not in scopes:problems.append(f'scope_group_map: {sc} has no observations at {atlas.state["commit"][:7]}')
    return problems
