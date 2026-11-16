"""First pass: China WFE market and domestic share by equipment group, from public data.

China market(group, year) = customs imports mapped to the group + domestic vendors' revenue in the group.
Segment definitions follow the Gartner-style segmentation used in sell-side reports; no third-party
values are used. Groups merge segments that customs cannot separate (see reference/segments.csv).
Domestic revenue has two layers: Atlas-reported category revenue, and bottom-up estimates for vendors
without usable filings (projects/unlisted_vendors), kept separate and labelled by method tier.
"""
import calendar
import pandas as pd
from sme_analysis import charts, manifest, reference
from sme_analysis.data import ROOT, num

ESTIMATES = ROOT/'projects'/'unlisted_vendors'/'estimates'

YEARS = [2023, 2024, 2025]
IMPORT_YEARS = [2021, 2022, 2023, 2024, 2025]
WFE_GROUPS = ['litho','deposition','dry_etch','process_control','cleaning_strip','cmp','doping','thermal','track_automation_other']
RELATION_RANK = {'eq':0,'approx':1,'as_reported':1,'ge':2,'gt':2,'approaching':2,'range':3,'le':4,'lt':4}
LABELS = {'litho':'Lithography','deposition':'Deposition','dry_etch':'Dry etch','process_control':'Process control','cleaning_strip':'Cleaning & strip',
          'cmp':'CMP','doping':'Implant','thermal':'Thermal','track_automation_other':'Track, automation & other'}
CHART = 'china_wfe_domestic_share_2025.png'

def fx_cny_per_usd(atlas):
    t=atlas.statistics('eurostat/fx_annual_per_eur.csv');t['v']=num(t['units_per_eur'])
    p=t.pivot(index='year',columns='currency',values='v');s=p['CNY']/p['USD'];s.index=s.index.astype(int);return s

def ytd_window(atlas):
    """Months and label for the like-for-like comparison: January to the latest month held."""
    last=int(atlas.statistics('china_customs/imports_hs8_monthly.csv')['period'].max()[5:7])
    return range(1,last+1),f'Jan-{calendar.month_abbr[last]}'

def imports_by_group(atlas, years=None, months=None):
    """Allocate customs imports to groups per reference/customs_segment_map.csv, with low/base/high for scenario amounts.

    By default: full calendar years in IMPORT_YEARS. With `months` (e.g. range(1,9)), each year is restricted to those
    months (and must have all of them); fixed annual USD amounts are scaled by len(months)/12.
    """
    years=years or IMPORT_YEARS;months=list(months) if months else list(range(1,13));scale=len(months)/12
    cmap=reference.load('customs_segment_map')
    hs=atlas.statistics('china_customs/imports_hs8_monthly.csv')
    pp=atlas.statistics('china_customs/imports_hs8_partner_province_monthly.csv')
    for t in (hs,pp):t['usd']=num(t['usd']);t['year']=t['period'].str[:4].astype(int);t['month']=t['period'].str[5:7].astype(int)
    hs,pp=hs[hs['month'].isin(months)],pp[pp['month'].isin(months)]
    detail=[]
    for (hs8,origin),rules in cmap.groupby(['hs8','origin_rule'],sort=False):
        if hs8 in set(hs['hs8']) and origin=='all':src,table=hs[hs['hs8']==hs8],'imports_hs8_monthly'
        else:
            src,table=pp[pp['hs8']==hs8],'imports_hs8_partner_province_monthly (8 origins x 14 provinces)'
            kind,_,code=origin.partition(':')
            if kind=='exclude':src=src[src['partner_code']!=code]
            elif kind=='only':src=src[src['partner_code']==code]
        for year in years:
            ys=src[src['year']==year]
            if ys['period'].nunique()<len(months):continue
            pool=ys['usd'].sum()
            for case in ('low','base','high'):
                left=pool
                for _,r in rules.sort_values('allocation',key=lambda s:s.str.startswith('residual')).iterrows():
                    kind,_,aid=r['allocation'].partition(':')
                    if kind in ('amount_usd','share'):
                        a=reference.assumption(aid);x={'low':a['low'],'base':a['value'],'high':a['high']}[case]
                        amt=min(left,x*scale if kind=='amount_usd' else pool*x);left-=amt
                    elif kind=='residual':amt=left;left=0
                    else:amt=pool
                    detail.append({'year':year,'hs8':hs8,'origin_rule':origin,'group_id':r['group_id'],'allocation':r['allocation'],'case':case,'usd':amt,'source_table':table})
    d=pd.DataFrame(detail)
    g=d.pivot_table(index=['year','group_id'],columns='case',values='usd',aggfunc='sum').reset_index()
    return d,g.rename(columns={'low':'imports_usd_low','base':'imports_usd','high':'imports_usd_high'})

def domestic_by_vendor(atlas, fx):
    """One revenue value per vendor x group x year from category-level Atlas observations, avoiding parent/child double counting."""
    obs=atlas.observations();seg=reference.load('segments');vendors=reference.load('vendors')
    cat_group={c:r['group_id'] for _,r in seg.iterrows() for c in r['atlas_categories'].split(';') if c}
    parent={c['category_id']:c.get('parent_category_id','') for c in atlas.registries['categories']}
    def ancestors(c):
        out=[]
        while parent.get(c):c=parent[c];out.append(c)
        return out
    include=set(vendors.loc[vendors['include']=='yes','entity_id'])
    smap=reference.load('scope_group_map').set_index('reporting_scope_id')
    rank=lambda t:t['relation'].map(RELATION_RANK).fillna(9)+(~t['reporting_basis'].isin(['original','current','current_period'])).astype(int)*0.5
    usd=lambda t,y:sum(v/fx[y] if u=='CNY' else v for v,u in zip(t['value_base'],t['base_unit']))
    # A scope in scope_group_map overrides its Atlas category (e.g. packaging lithography filed under lithography).
    r=obs[(obs['metric_id']=='revenue')&(obs['period_kind']=='annual')&(~obs['superseded'])&obs['entity_id'].isin(include)
          &obs['category_id'].isin(cat_group)&~obs['reporting_scope_id'].isin(smap.index)&obs['base_unit'].isin(['CNY','USD'])&obs['value_base'].notna()].copy()
    r['year']=r['period_end'].str[:4].astype(int);r=r[r['year'].isin(YEARS)];r['group_id']=r['category_id'].map(cat_group)
    r['rank']=rank(r)
    rows=[]
    for (e,g,y),grp in r.groupby(['entity_id','group_id','year']):
        present=set(grp['category_id'])
        top=grp[[not (set(ancestors(c))&present) for c in grp['category_id']]]
        chosen=top.sort_values(['rank','observation_id']).groupby('category_id').head(1)
        rel=set(chosen['relation'])
        rows.append({'entity_id':e,'group_id':g,'year':y,'value_usd':usd(chosen,y),
            'basis':'lower bound' if rel&{'gt','ge','approaching'} else 'approximate' if 'approx' in rel else 'reported',
            'categories':';'.join(sorted(chosen['category_id'])),'geography':';'.join(sorted(set(chosen['geography']))),
            'observation_ids':';'.join(chosen['observation_id']),'in_share':True,'review_status':';'.join(sorted(set(chosen['review_status'])))})
    have={(x['entity_id'],x['group_id'],x['year']) for x in rows}
    # Mapped scopes: one observation per scope, summed across the scopes mapped to a group (map only non-overlapping scopes).
    b=obs[(obs['metric_id']=='revenue')&(obs['period_kind']=='annual')&(~obs['superseded'])&obs['entity_id'].isin(include)
          &obs['reporting_scope_id'].isin(smap.index)&obs['base_unit'].isin(['CNY','USD'])&obs['value_base'].notna()].copy()
    b['year']=b['period_end'].str[:4].astype(int);b=b[b['year'].isin(YEARS)];b['group_id']=b['reporting_scope_id'].map(smap['group_id'])
    # in_share: yes = counted; no = held out (reported, not in shares); exclude = totals or parts that would double count.
    flag=b['reporting_scope_id'].map(smap['in_share']);b=b[flag!='exclude'].copy()
    b['in_share']=b['reporting_scope_id'].map(smap['in_share'])!='no';b['rank']=rank(b)
    for (e,g,y,share),grp in b.groupby(['entity_id','group_id','year','in_share']):
        if (e,g,y) in have:continue
        chosen=grp.sort_values(['rank','observation_id']).groupby('reporting_scope_id').head(1)
        rows.append({'entity_id':e,'group_id':g,'year':y,'value_usd':usd(chosen,y),'basis':'mapped basket','categories':';'.join(sorted(chosen['reporting_scope_id'])),
                     'geography':';'.join(sorted(set(chosen['geography']))),'observation_ids':';'.join(chosen['observation_id']),
                     'in_share':bool(share),'review_status':';'.join(sorted(set(chosen['review_status'])))})
    dom=pd.DataFrame(rows);dom['value_usd_low']=dom['value_usd'];dom['value_usd_high']=dom['value_usd'];dom['adjustment']=''
    dom=apply_splits(dom,obs,fx,include);dom=apply_geography(dom)
    company=obs[(obs['metric_id']=='revenue')&(obs['period_kind']=='annual')&obs['entity_id'].isin(include)&(obs['category_id']=='all_businesses')]
    company_years={(e,int(p[:4])) for e,p in zip(company['entity_id'],company['period_end']) if p[:4].isdigit()}
    return dom,company_years

def apply_splits(dom, obs, fx, include):
    """Replace rows with reference/product_splits.csv allocations of a reported basket (low/base/high shares).

    A split for (entity, scope, year) supersedes every row for the (entity, group, year) pairs it allocates to, and any
    scope-route row built from the same scope in that year. Bounded lines (e.g. NAURA "over CNY 10bn") are handled this way.
    """
    sp=reference.load('product_splits')
    if not len(sp):return dom
    for c in ('share_low','share_base','share_high'):sp[c]=sp[c].astype(float)
    sp['year']=sp['year'].astype(int);sp=sp[sp['entity_id'].isin(include)&sp['year'].isin(YEARS)]
    b=obs[(obs['metric_id']=='revenue')&(obs['period_kind']=='annual')&(~obs['superseded'])&obs['base_unit'].isin(['CNY','USD'])
          &obs['geography'].isin(['all_reported_geographies',''])].copy()
    b['year']=b['period_end'].str[:4].astype(int)
    usd=lambda v,u,y:v/fx[y] if u=='CNY' else v
    targets={(e,g,y) for e,g,y in zip(sp['entity_id'],sp['group_id'],sp['year'])}
    scopes={(e,sc,y) for e,sc,y in zip(sp['entity_id'],sp['reporting_scope_id'],sp['year'])}
    keep=[(e,g,y) not in targets and not any((e,c,y) in scopes for c in cats.split(';')) for e,g,y,cats in zip(dom['entity_id'],dom['group_id'],dom['year'],dom['categories'])]
    rows=[]
    for (e,sc,y),grp in sp.groupby(['entity_id','reporting_scope_id','year']):
        basket=b[(b['entity_id']==e)&(b['reporting_scope_id']==sc)&(b['year']==y)].sort_values('observation_id')
        if not len(basket):raise ValueError(f'product_splits: no basket value for {e} {sc} {y}')
        o=basket.iloc[0];v=usd(o['value_base'],o['base_unit'],y)
        for _,r in grp.iterrows():
            rows.append({'entity_id':e,'group_id':r['group_id'],'year':y,'value_usd':v*r['share_base'],'value_usd_low':v*r['share_low'],'value_usd_high':v*r['share_high'],
                'basis':f'split (tier {r["method_tier"]})','categories':sc,'geography':o['geography'],'observation_ids':o['observation_id'],'in_share':True,
                'review_status':o['review_status'],'adjustment':r['split_id']})
    return pd.concat([dom[keep],pd.DataFrame(rows)],ignore_index=True)

def apply_geography(dom):
    """Scale rows by the China share in reference/geography_splits.csv (named exceptions to A-GEO-ALL-AS-CHINA)."""
    geo=reference.load('geography_splits')
    for _,r in geo.iterrows():
        m=(dom['entity_id']==r['entity_id'])&(dom['year']==int(r['year']))
        for col,c in (('value_usd','base'),('value_usd_low','low'),('value_usd_high','high')):dom.loc[m,col]=dom.loc[m,col]*float(r[f'china_share_{c}'])
        dom.loc[m,'geography']='mainland China (geography_splits)'
        dom.loc[m,'adjustment']=dom.loc[m,'adjustment'].map(lambda a:';'.join(filter(None,[a,f'geo-{r["entity_id"]}-{r["year"]}'])))
    return dom

def estimate_layer(dom, fx):
    """Unlisted-vendor estimates (CNY m) in USD, with rows superseded by the Atlas numerator or not China-based marked as dropped.

    A row is superseded when its `overlaps` field leads with an entity id that has category revenue in the
    Atlas numerator for that year (e.g. a long-tail firm later filed into the Atlas). Global rows stay out
    until converted to China sales.
    """
    have={(e,y) for e,y in zip(dom['entity_id'],dom['year'])}
    rows=[]
    for p in sorted(ESTIMATES.glob('*.csv')):
        est=pd.read_csv(p,dtype=str,keep_default_na=False)
        for _,r in est.iterrows():
            y=int(r['year'])
            if y not in YEARS:continue
            lead=r['overlaps'].split(':')[0].strip()
            drop=('geography global: not converted to China sales' if r['geography']=='global'
                  else f'superseded: Atlas numerator has {lead} for {y}' if (lead,y) in have else '')
            rows.append({'firm_id':r['firm_id'],'unit':r['unit'],'group_id':r['group_id'],'year':y,'method_tier':r['method_tier'],'status':r['status'],
                         **{f'usd_{c}':float(r[f'revenue_cny_m_{c}'])*1e6/fx[y] for c in ('low','base','high')},'dropped':drop})
    return pd.DataFrame(rows)

def cepea_frontend(atlas, fx):
    c=atlas.statistics('cepea/semiconductor_equipment_annual.csv')
    fe=c[c['category_en'].isin(['Wafer (chip) fab equipment','IC chip (wafer) manufacturing equipment'])].copy()
    fe['year']=fe['year'].astype(int);fe['cny']=num(fe['revenue_cny_100m'])*1e8;fe['usd']=[v/fx[y] for v,y in zip(fe['cny'],fe['year'])]
    return fe.set_index('year')['usd']

def md_table(df, cols, fmt=None):
    fmt=fmt or {}
    lines=['| '+' | '.join(cols)+' |','|'+'---|'*len(cols)]
    for _,r in df.iterrows():lines.append('| '+' | '.join(fmt.get(c,str)(r[c]) for c in cols)+' |')
    return '\n'.join(lines)

def run(atlas, out, preview=None):
    fx=fx_cny_per_usd(atlas)
    detail,imp=imports_by_group(atlas);dom,company_years=domestic_by_vendor(atlas,fx);cepea=cepea_frontend(atlas,fx)
    est=estimate_layer(dom,fx);use=est[(est['dropped']=='')&est['group_id'].isin(WFE_GROUPS)]
    vendors=reference.load('vendors').set_index('entity_id');stack=reference.load('hbm_tool_stack')
    names={e['entity_id']:e.get('name',e['entity_id']) for e in atlas.registries['entities']}
    names.update(vendors['name'].to_dict())
    rows=[]
    for y in YEARS:
        for g in WFE_GROUPS:
            i=imp[(imp['year']==y)&(imp['group_id']==g)];dg=dom[(dom['year']==y)&(dom['group_id']==g)]
            d=dg[dg['in_share']];held=dg[~dg['in_share']];e=use[(use['year']==y)&(use['group_id']==g)]
            imps=[float(i[c].sum()) if len(i) else float('nan') for c in ('imports_usd_low','imports_usd','imports_usd_high')];iu=imps[1]
            du=float(d['value_usd'].sum());dl=float(d['value_usd_low'].sum());dh=float(d['value_usd_high'].sum())
            el,eb,eh=(float(e[f'usd_{c}'].sum()) for c in ('low','base','high'))
            share=du/(du+iu) if len(d) and iu==iu else float('nan')
            # Ranges pair the domestic low with the highest imports case and the domestic high with the lowest.
            # Scenario cases are not ordered by value (a residual shrinks as carve-outs grow), so pair with the actual max and min.
            ihi,ilo=max(imps),min(imps)
            cases=[dl/(dl+ihi),du/(du+iu),dh/(dh+ilo)] if len(d) and len(i) else [float('nan')]
            tot=lambda dv,ev,x:(dv+ev)/(dv+ev+x) if (len(d) or len(e)) and x==x else float('nan')
            cands=sorted({c.strip() for v in stack.loc[stack['group_id']==g,'domestic_candidates'] for c in v.split(';') if c.strip() and not c.startswith('(')})
            rows.append({'year':y,'group_id':g,'imports_usd_m':iu/1e6,'domestic_revenue_usd_m':du/1e6 if len(d) else float('nan'),
                'provisional_domestic_share':share,'share_min':min(cases),'share_max':max(cases),
                'estimates_usd_m_low':el/1e6,'estimates_usd_m_base':eb/1e6,'estimates_usd_m_high':eh/1e6,
                'domestic_revenue_usd_m_low':dl/1e6 if len(d) else float('nan'),'domestic_revenue_usd_m_high':dh/1e6 if len(d) else float('nan'),
                'share_with_estimates':tot(du,eb,iu),'share_with_estimates_min':tot(dl,el,max(imps)),'share_with_estimates_max':tot(dh,eh,min(imps)),
                'held_out_usd_m':float(held['value_usd'].sum())/1e6,
                'vendors_with_category_revenue':'; '.join(sorted(names.get(v,v) for v in d['entity_id'])),
                'pending_evidence_vendors':'; '.join(sorted(names.get(v,v) for v,st in zip(d['entity_id'],d['review_status']) if 'pending' in st)),
                'estimated_firms':'; '.join(f'{f} ({t})' for f,t in sorted({(f,''.join(sorted(set(e.loc[e['firm_id']==f,'method_tier'])))) for f in e['firm_id']})),
                'numerator_basis':'; '.join(sorted(set(d['basis']))),'candidate_vendors':'; '.join(cands)})
    table=pd.DataFrame(rows)
    detail.to_csv(out/'imports_by_hs8_allocation.csv',index=False);imp.to_csv(out/'imports_by_group.csv',index=False)
    dom.assign(name=dom['entity_id'].map(names)).to_csv(out/'domestic_revenue_by_vendor.csv',index=False)
    est.to_csv(out/'estimates_layer.csv',index=False,float_format='%.0f')
    table.to_csv(out/'segment_table.csv',index=False,float_format='%.4f')
    # Coverage of the numerator against CEPEA's domestic front-end total (both in USD at A-FX-CNY-USD).
    cov=[];non_wfe=set(dom['entity_id'])-set(dom.loc[dom['group_id'].isin(WFE_GROUPS),'entity_id'])  # e.g. test-only vendors
    for y in YEARS:
        dy=dom[(dom['year']==y)&dom['group_id'].isin(WFE_GROUPS)&dom['in_share']];ours=dy['value_usd'].sum();ours_low=dy['value_usd_low'].sum();ey=use[use['year']==y]
        c=cepea.get(y,float('nan'))
        cov.append({'year':y,'atlas_category_revenue_usd_m':ours/1e6,'estimates_usd_m_low':ey['usd_low'].sum()/1e6,'estimates_usd_m_base':ey['usd_base'].sum()/1e6,
                    'estimates_usd_m_high':ey['usd_high'].sum()/1e6,'cepea_frontend_usd_m':c/1e6,
                    'coverage_low':ours_low/c,'coverage':ours/c,'coverage_with_estimates':(ours+ey['usd_base'].sum())/c,
                    'company_level_only':'; '.join(sorted(names.get(e,e) for e,yy in company_years if yy==y and e not in set(dom.loc[dom['year']==y,'entity_id']) and e not in non_wfe))})
    cov=pd.DataFrame(cov);cov.to_csv(out/'numerator_coverage.csv',index=False,float_format='%.4f')
    # Fab-automation sub-view: domestic wafer-handling revenue against AMHS imports (84864031), with the 84864039 sensitivity.
    cat=atlas.observations().set_index('observation_id')['category_id']
    handling=dom[dom['observation_ids'].map(lambda ids:all(str(cat.get(o,'')).startswith(('wafer_handling','fab_automation')) for o in ids.split(';')))]
    auto=[]
    for y in YEARS:
        dm=handling.loc[(handling['year']==y)&handling['in_share'],'value_usd'].sum()
        amhs=detail.loc[(detail['year']==y)&(detail['hs8']=='84864031')&(detail['case']=='base'),'usd'].sum()
        extra=detail.loc[(detail['year']==y)&(detail['hs8']=='84864039')&(detail['case']=='high')&(detail['group_id']=='track_automation_other'),'usd'].sum()
        auto.append({'year':y,'domestic_handling_usd_m':dm/1e6,'amhs_imports_usd_m':amhs/1e6,'handling_39_high_usd_m':extra/1e6,
                     'share_base':dm/(dm+amhs) if dm+amhs else float('nan'),'share_high_imports':dm/(dm+amhs+extra) if dm+amhs else float('nan'),
                     'vendors':'; '.join(sorted(names.get(e,e) for e in set(handling.loc[handling['year']==y,'entity_id'])))})
    auto=pd.DataFrame(auto);auto.to_csv(out/'automation_subview.csv',index=False,float_format='%.4f')
    pct=lambda v:'n/a' if v!=v else f'{v:.0%}';m=lambda v:'n/a' if v!=v else f'{v:,.0f}'
    rng=lambda a,b:'n/a' if a!=a else f'{a:.0%}–{b:.0%}'
    # v1 outlook: market size and share with estimates (the headline basis), 2023->25 change and year-to-date import momentum.
    _,ytd=imports_by_group(atlas,years=[2025,2026],months=ytd_window(atlas)[0])
    ytdw=ytd.pivot(index='group_id',columns='year',values='imports_usd')
    ly=table[table['year']==YEARS[-1]].set_index('group_id');fy=table[table['year']==YEARS[0]].set_index('group_id')
    mkt=lambda g:ly.at[g,'imports_usd_m']+(0 if ly.at[g,'domestic_revenue_usd_m']!=ly.at[g,'domestic_revenue_usd_m'] else ly.at[g,'domestic_revenue_usd_m'])+ly.at[g,'estimates_usd_m_base']
    order=sorted(WFE_GROUPS,key=mkt,reverse=True)
    outlook=pd.DataFrame([{'group':LABELS[g],'china_market_usd_m':mkt(g),'domestic_share':ly.at[g,'share_with_estimates'],
        'range':rng(ly.at[g,'share_with_estimates_min'],ly.at[g,'share_with_estimates_max']),
        'change_pp':(ly.at[g,'share_with_estimates']-fy.at[g,'share_with_estimates'])*100,
        'imports_ytd':ytdw.at[g,2026]/ytdw.at[g,2025]-1 if g in ytdw.index else float('nan')} for g in order])
    sh=lambda g:ly.at[g,'share_with_estimates']
    title=(f'Domestic vendors supply {sh("dry_etch"):.0%} of China\'s dry-etch market and {sh("deposition"):.0%} of deposition,\n'
           f'but {sh("process_control"):.0%} of process control and {sh("litho"):.0%} of lithography')
    short={'process_control':'Process\ncontrol','track_automation_other':'Track,\nautomation\n& other','cleaning_strip':'Cleaning\n& strip'}
    charts.marimekko([{'label':LABELS[g],'short':short.get(g,LABELS[g]),'market':mkt(g),'share':sh(g),'share_min':ly.at[g,'share_with_estimates_min'],'share_max':ly.at[g,'share_with_estimates_max']} for g in order],
        out/CHART,title,f'China wafer-fab equipment market by segment, {YEARS[-1]}. Market = customs imports + domestic vendors\' revenue (Atlas layer plus unlisted-vendor estimates).',
        f'Source: China customs (imports by HS code, allocated per reference/customs_segment_map.csv); SME Equipment Atlas {atlas.state["commit"][:7]} (issuer filings); '
        'unlisted-vendor estimates (tiers D-E). Tier 3 working research, provisional; all judgement rows proposed. sme-atlas-analysis/china_share_by_segment.')
    latest=table[table['year']==YEARS[-1]].copy();latest['range']=[rng(a,b) for a,b in zip(latest['share_with_estimates_min'],latest['share_with_estimates_max'])]
    wide=table.pivot(index='group_id',columns='year',values=['provisional_domestic_share','share_with_estimates']).reindex(WFE_GROUPS)
    trend=pd.DataFrame({'group_id':WFE_GROUPS,**{f'{y} Atlas / with est.':[f'{pct(wide.loc[g,("provisional_domestic_share",y)])} / {pct(wide.loc[g,("share_with_estimates",y)])}' for g in WFE_GROUPS] for y in YEARS}})
    dropped=est[est['dropped']!='']
    summary=['# China Share by Segment v1','',
      f'> Tier 3, generated by `sme-atlas-analysis` project `china_share_by_segment` against Atlas `{atlas.state["commit"][:7]}`. Provisional: see the gaps before citing any figure. Supersedes the first pass.','',
      f'## Outlook ({YEARS[-1]})','',f'![[{CHART}]]','',
      md_table(outlook,['group','china_market_usd_m','domestic_share','range','change_pp','imports_ytd'],
               {'china_market_usd_m':m,'domestic_share':pct,'change_pp':lambda v:f'{v:+.0f}pp','imports_ytd':lambda v:'n/a' if v!=v else f'{v:+.0%}'}),'',
      f'Columns: China market = imports + domestic revenue + estimates (USD m); domestic share with estimates and its low–high range; change in that share since {YEARS[0]} (percentage points); imports Jan–Aug 2026 against Jan–Aug 2025.','',
      f'Numerator coverage against CEPEA\'s domestic front-end total is {cov.iloc[-1]["coverage_low"]:.0%} on floors, {cov.iloc[-1]["coverage"]:.0%} base and {cov.iloc[-1]["coverage_with_estimates"]:.0%} with estimates in {YEARS[-1]}. The HBM step view is in `hbm_step_market` (HBM Step Market Lookup).','',
      '**Method.** China market (group, year) = customs imports mapped to the group + domestic vendors\' revenue in the group. Groups merge segments that customs cannot separate.',
      '','Domestic revenue has two layers:',
      '- **Atlas layer.** Issuer-reported category revenue. Where a vendor reports only a mixed product basket, a scope mapping (`reference/scope_group_map.csv`) assigns it to one group and overrides the Atlas category.',
      '- **Estimate layer.** Bottom-up estimates for SMEE, SiCarrier, CETC units and a long tail (`projects/unlisted_vendors`). Rows are tiered A–E and all are still `proposed`. Rows for firms that the Atlas numerator now covers are dropped, as are global (non-China) rows.',
      '','**Estimation standards applied** (`docs/estimation_standards.md`; all rows `proposed`):',
      '- **Product splits** (`reference/product_splits.csv`). NAURA lines reported only as floors ("over CNY 10bn") carry the floor as low, a growth-carried base and a capped high (A-NAURA-LINE-GROWTH); Kingsemi 2025 track vs cleaning; Hwatsing CMP vs thinning; Yitang 2025 strip; Hwatsing implant from the Xinyu earn-out bracket. ACM Shanghai uses its own product lines in every year.',
      '- **Geography** (`reference/geography_splits.csv`). Yitang is scaled to its reported 70% mainland share (Mattson sells overseas); ACM Shanghai to 97–99.5%. Everyone else is treated as China supply, an upper bound (A-GEO-ALL-AS-CHINA).',
      '- **Overlaps.** NAURA has consolidated Kingsemi since 2025-06-23, but NAURA\'s modelled lines exclude it (its 2025 lines are carried from the pre-consolidation 2024 base at a growth factor that excludes Kingsemi\'s H2 revenue, and A-KINGSEMI-H2-IN-NAURA also removes Kingsemi from the residual cap). AMEC holds Sizone, but AMEC reports no CMP line, so the two never overlap in one group.',
      '','Revenue is converted at Eurostat-derived CNY/USD (A-FX-CNY-USD). The CMP range reflects A-CMP-IN-84862090. Ranges pair the domestic and estimate lows with the highest imports case, and the highs with the lowest.','',
      '**Automation.** `track_automation_other` now includes AMHS imports (84864031, in full), plus up to half of 84864039 in the high case (A-WAFER-HANDLING-IN-84864039; base 0). The rest of 84864039 is flat-panel handling and robots imported as tool modules. Domestic AMHS (Mifei) and sorters (Jingyi Automation) are in the numerator. Tracks, AMHS and other apparatus remain one group because 84862090 cannot be split.','',
      f'## {YEARS[-1]} by group (USD m)','',
      md_table(latest,['group_id','imports_usd_m','domestic_revenue_usd_m','estimates_usd_m_base','provisional_domestic_share','share_with_estimates','range','estimated_firms'],
               {'imports_usd_m':m,'domestic_revenue_usd_m':m,'estimates_usd_m_base':m,'provisional_domestic_share':pct,'share_with_estimates':pct}),'',
      '`provisional_domestic_share` uses the Atlas layer only. `share_with_estimates` adds the estimate base. Tier letters follow `docs/estimation_standards.md` (E = ×0.5–×2).','',
      '## Shares by year (Atlas only / with estimates)','',md_table(trend,list(trend.columns)),'',
      '## Numerator coverage vs CEPEA front-end total','',
      md_table(cov,['year','atlas_category_revenue_usd_m','estimates_usd_m_base','cepea_frontend_usd_m','coverage_low','coverage','coverage_with_estimates','company_level_only'],
               {'atlas_category_revenue_usd_m':m,'estimates_usd_m_base':m,'cepea_frontend_usd_m':m,'coverage_low':pct,'coverage':pct,'coverage_with_estimates':pct}),'',
      'CEPEA is a cross-check, not a ceiling: its survey can exclude non-reporting or loss-making firms, and our numerator includes power, compound and LED lines that its front-end category may not. `coverage_low` uses the floors and low splits.','',
      '## Fab automation sub-view (USD m)','',
      'Domestic fab-automation and sorter revenue (Atlas categories `fab_automation*` and `wafer_handling_sorter`) against AMHS imports (84864031). `share_high_imports` adds half of 84864039.','',
      md_table(auto,['year','domestic_handling_usd_m','amhs_imports_usd_m','share_base','share_high_imports','vendors'],
               {'domestic_handling_usd_m':m,'amhs_imports_usd_m':m,'share_base':pct,'share_high_imports':pct}),'',
      f'**Dropped estimate rows.** {len(dropped)} rows were dropped (`estimates_layer.csv`, column `dropped`):',
      *[f'- {k}: {n}' for k,n in dropped['dropped'].str.replace(r' for \d{4}$','',regex=True).value_counts().items()],'',
      '## Gaps blocking a full replication','',
      '- **Evidence status.** The long-tail Atlas rows (Leuven, Yadian, Mifei, Jingyi Automation, CFMEE and the test firms; Atlas PR #101) are `pending` independent verification. All estimate rows are `proposed`. `pending_evidence_vendors` in `segment_table.csv` flags the affected cells.',
      '- **Estimate-driven groups.** Lithography (SMEE, tier E front-end) and doping (CETC implant, tier D) rest almost entirely on estimates. SiCarrier (tier E) adds a large, uncertain slice to 2025 process control, etch and deposition.',
      '- **Domestic numerator.** NAURA (about a third of the numerator) is modelled from bounded lines; exact product-line revenue would narrow every front-end range. Leadmicro 2024 and Secote remain company-level only. Yitang 2023–24 geography is carried back from 2025.',
      '- **Import side.** 84862090 mixes tracks, wet cleaning and back-end tools. Cleaning (A-CLEAN-IN-84862090) and back-end (A-BACKEND-IN-84862090) are carved out as proposed scenario shares; the track/automation residual moves inversely with them. E-beam inspection/CD-SEM and X-ray are not separable at 8 digits. Cleaning and strip cannot be split within 84862049. Settled import figures are in the `china_imports` project.',
      '- **Process control.** The numerator includes e-beam inspection and CD-SEM (Dongfang Jingyuan), but imports cover optical tools only (90314100), so the share is an upper bound on a like-for-like basis.',
      '- **Foreign vendor shares (the sell-side companion chart).** Not attempted: needs foreign vendors\' China revenue by segment, which is not public.']
    (out/'summary.md').write_text('\n'.join(summary)+'\n')
    manifest.write(out,'china_share_by_segment',[atlas],['A-FX-CNY-USD','A-CMP-IN-84862090','A-CLEAN-IN-84862090','A-BACKEND-IN-84862090','A-WAFER-HANDLING-IN-84864039','A-GEO-ALL-AS-CHINA','A-NO-TIMING-LAG','A-NAURA-LINE-GROWTH','A-KINGSEMI-H2-IN-NAURA'],
                   'First pass; Atlas layer plus proposed unlisted-vendor estimate layer, reported separately.',inputs=sorted(ESTIMATES.glob('*.csv')))
    return {'years':YEARS,'groups':len(WFE_GROUPS),'numerator_coverage':cov[['year','coverage','coverage_with_estimates']].round(3).to_dict('records')}
