"""Time series out of the Atlas for charts: one value per period, best evidence first, with provenance.

A query names an entity and a metric, optionally narrowed by category, reporting scope and geography. Where several
observations cover one period, the exact figure beats an approximate one, which beats a bound; current reporting beats
restated vintages. Money is returned in millions of its native currency; counts and ratios as reported.
"""
from .data import Atlas

RELATION_RANK = {'eq':0,'approx':1,'as_reported':1,'ge':2,'gt':2,'approaching':2,'range':3,'le':4,'lt':4}
BOUND = {'ge','gt','approaching'}
MONEY = {'CNY':'CNY m','USD':'USD m','EUR':'EUR m','JPY':'JPY m','KRW':'KRW m'}

def period_label(kind, start, end):
    if kind=='annual':return end[:4]
    if kind=='interim':
        m={'06':'H1','09':'9M'}.get(end[5:7],end[5:7]);return f'{end[:4]} {m}' if start[5:7]=='01' else end[:7]
    if kind=='quarter':return f'{end[:4]} Q{(int(end[5:7])-1)//3+1}'
    if kind=='as_of':return end[:7]
    return f'{start[:4]}–{end[:4]}'

def atlas_series(atlas:Atlas, entity, metric, category=None, scope=None, geography='all_reported_geographies', period_kind='annual', start_year=None, platform=None, unit=None):
    """Return {'unit', 'points': [{period, value, relation, observation_id, bound}]} sorted by period."""
    o=atlas.observations()
    t=o[(o['entity_id']==entity)&(o['metric_id']==metric)&(o['period_kind']==period_kind)&(~o['superseded'])&o['value_base'].notna()]
    if category:t=t[t['category_id']==category]
    if scope:t=t[t['reporting_scope_id']==scope]
    if unit:t=t[t['unit']==unit]
    if platform:
        ids={x['observation_id'] for x in atlas.registries['observations'] if x.get('platform_id')==platform};t=t[t['observation_id'].isin(ids)]
    if geography is not None:t=t[t['geography'].isin([geography,''])] if geography=='all_reported_geographies' else t[t['geography']==geography]
    if start_year:t=t[t['period_end'].str[:4].astype(int)>=int(start_year)]
    if not len(t):
        # balance-sheet stocks (deferred expenses, PP&E, backlog) are point-in-time: retry an annual query as as_of
        if period_kind=='annual':return atlas_series(atlas,entity,metric,category,scope,geography,'as_of',start_year,platform,unit)
        return {'unit':'','points':[]}
    t=t.assign(rank=t['relation'].map(RELATION_RANK).fillna(9)+(~t['reporting_basis'].isin(['original','current','current_period'])).astype(int)*0.5,
               label=[period_label(period_kind,s,e) for s,e in zip(t['period_start'],t['period_end'])])
    t=t.sort_values(['rank','observation_id']).groupby('label',as_index=False).head(1).sort_values('period_end')
    base=t['base_unit'].iloc[0];money=base in MONEY
    unit=MONEY.get(base,t['unit'].iloc[0] if not base else base)
    pts=[{'period':r['label'],'value':(r['value_base']/1e6 if money else r['value_base']),'relation':r['relation'],
          'observation_id':r['observation_id'],'bound':r['relation'] in BOUND} for _,r in t.iterrows()]
    return {'unit':unit,'points':pts}
