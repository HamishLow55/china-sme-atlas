"""Market lookup per HBM process step: China imports, domestic revenue and domestic share, with the basis stated.

Front-end and TSV steps inherit their equipment group from `china_share_by_segment` (group-level: the step is a
sub-application). Back-end and test steps use a step pool: named customs codes against named domestic vendors'
revenue, where one exists (reference/hbm_step_market_map.csv). Steps without a separable market say so.
Per-step market figures in the report come from here.
"""
import pandas as pd
from sme_analysis import manifest, reference
from sme_analysis.cli import project_module

YEARS = [2023, 2024, 2025]
EBEAM = ('inspection_ebeam', 'inspection_review_sem', 'metrology_cd_sem')

def run(atlas, out, preview=None):
    share=project_module('china_share_by_segment')
    fx=share.fx_cny_per_usd(atlas)
    detail,imp=share.imports_by_group(atlas,years=YEARS)
    ytd_detail,ytd=share.imports_by_group(atlas,years=[2025,2026],months=share.ytd_window(atlas)[0])
    dom,_=share.domestic_by_vendor(atlas,fx);est=share.estimate_layer(dom,fx);est=est[est['dropped']=='']
    names={e['entity_id']:e.get('name',e['entity_id']) for e in atlas.registries['entities']}
    names.update(reference.load('vendors').set_index('entity_id')['name'].to_dict())
    smap=reference.load('hbm_step_market_map');stack=reference.load('hbm_tool_stack').set_index('step_id')
    cat=atlas.observations().set_index('observation_id')['category_id']
    ratio=lambda a,b:a/(a+b) if a+b else float('nan')

    def group_imports(d,g,y):
        t=d[(d['year']==y)&(d['group_id']==g)];return {c:float(t.loc[t['case']==c,'usd'].sum()) for c in ('low','base','high')} if len(t) else None
    def pool_imports(d,codes,y):
        t=d[(d['year']==y)&d['hs8'].isin(codes)&(d['case']=='base')]
        # Pool codes are allocated in full to one group, so the base case is the code total.
        t=t.drop_duplicates(['hs8']);v=float(t['usd'].sum());return {'low':v,'base':v,'high':v} if len(t) else None

    rows=[];numer={}  # (step, year) -> domestic numerator rows, for the constant-vendor share
    for _,m in smap.iterrows():
        s=m['step_id'];codes=[c for c in m['import_hs8'].split(';') if c]
        ents=[e for e in m['domestic_entities'].split(';') if e]
        for y in YEARS:
            base={'step_id':s,'hbm_stage':stack.at[s,'hbm_stage'],'tool_family':stack.at[s,'tool_family'],'year':y,'market_basis':m['market_basis'],'note':m['note']}
            if m['market_basis']=='none':
                held=dom[(dom['year']==y)&(dom['group_id']==m['group_id'])&~dom['in_share']]
                rows.append({**base,'basis_label':'no separable market','group_or_pool':'','held_out_vendors':'; '.join(sorted(names.get(e,e) for e in held['entity_id']))});continue
            if m['market_basis']=='group':
                im=group_imports(detail,m['group_id'],y);d=dom[(dom['year']==y)&(dom['group_id']==m['group_id'])&dom['in_share']]
                label=f'group-level ({m["group_id"]})';pool=m['group_id']
            else:
                im=pool_imports(detail,codes,y);g=dom[(dom['year']==y)&(dom['group_id']==m['group_id'])]
                d=g[g['in_share']&(g['entity_id'].isin(ents) if ents!=['*'] else True)]
                label=f'step pool ({"+".join(codes)})';pool='+'.join(codes)
            held=dom[(dom['year']==y)&(dom['group_id']==m['group_id'])&~dom['in_share']]
            if m['market_basis']=='pool' and ents!=['*']:held=held[held['entity_id'].isin(ents)]  # pools hold out only their own firms
            dl,db,dh=(float(d[c].sum()) for c in ('value_usd_low','value_usd','value_usd_high'))
            numer[(s,y)]=(d,im)
            r={**base,'basis_label':label,'group_or_pool':pool,'imports_usd_m':im['base']/1e6 if im else float('nan'),
               'domestic_usd_m':db/1e6 if len(d) else float('nan'),'domestic_usd_m_low':dl/1e6 if len(d) else float('nan'),'domestic_usd_m_high':dh/1e6 if len(d) else float('nan'),
               'share_base':ratio(db,im['base']) if im and len(d) else float('nan'),
               'share_min':ratio(dl,max(im.values())) if im and len(d) else float('nan'),'share_max':ratio(dh,min(im.values())) if im and len(d) else float('nan'),
               'domestic_vendors':'; '.join(sorted(names.get(e,e) for e in set(d['entity_id']))),
               'held_out_usd_m':float(held['value_usd'].sum())/1e6,'held_out_vendors':'; '.join(sorted(names.get(e,e) for e in set(held['entity_id'])))}
            if m['market_basis']=='group':
                eb=float(est.loc[(est['year']==y)&(est['group_id']==m['group_id']),'usd_base'].sum())
                r['share_with_estimates']=ratio(db+eb,im['base']) if im else float('nan')
                yi=[group_imports(ytd_detail,m['group_id'],yy) for yy in (2025,2026)]
            else:
                yi=[pool_imports(ytd_detail,codes,yy) for yy in (2025,2026)]
            if y==YEARS[-1] and all(yi):r.update({'imports_ytd_2025_usd_m':yi[0]['base']/1e6,'imports_ytd_2026_usd_m':yi[1]['base']/1e6})
            rows.append(r)
    # Constant-vendor share: the numerator restricted to vendors reported in every year, so that a vendor entering the
    # Atlas (or a pool) does not read as localisation. Shown beside, not instead of, the headline share.
    for r in rows:
        if r['market_basis']=='none' or (r['step_id'],r['year']) not in numer:continue
        sets=[set(numer[(r['step_id'],y)][0]['entity_id']) for y in YEARS if (r['step_id'],y) in numer and len(numer[(r['step_id'],y)][0])]
        keep=set.intersection(*sets) if sets else set()
        d,im=numer[(r['step_id'],r['year'])];dk=d[d['entity_id'].isin(keep)]
        r['constant_vendors']='; '.join(sorted(names.get(e,e) for e in keep))
        r['share_constant_vendors']=ratio(float(dk['value_usd'].sum()),im['base']) if im and len(dk) else float('nan')
    # Process-control numerator sensitivity: 90314100 imports against a numerator without Dongfang Jingyuan or e-beam-only
    # categories. Modality allocation is incomplete (Jingce's basket may hold e-beam tools), so this is a sensitivity on
    # the numerator, not a like-for-like optical share.
    for y in YEARS:
        im=group_imports(detail,'process_control',y)
        d=dom[(dom['year']==y)&(dom['group_id']=='process_control')&dom['in_share']&(dom['entity_id']!='djel')]
        d=d[~d['observation_ids'].map(lambda ids:all(str(cat.get(o,'')).startswith(EBEAM) for o in ids.split(';')))]
        db=float(d['value_usd'].sum())
        rows.append({'step_id':'base_die_process_control (numerator sensitivity)','hbm_stage':'DRAM/base die (front end)','tool_family':'Process control, numerator sensitivity','year':y,
            'market_basis':'group','basis_label':'numerator sensitivity: process_control imports vs numerator without Dongfang Jingyuan or e-beam-only categories','group_or_pool':'process_control',
            'imports_usd_m':im['base']/1e6,'domestic_usd_m':db/1e6,'domestic_usd_m_low':float(d['value_usd_low'].sum())/1e6,'domestic_usd_m_high':float(d['value_usd_high'].sum())/1e6,
            'share_base':ratio(db,im['base']),'share_min':ratio(float(d['value_usd_low'].sum()),max(im.values())),'share_max':ratio(float(d['value_usd_high'].sum()),min(im.values())),
            'domestic_vendors':'; '.join(sorted(names.get(e,e) for e in set(d['entity_id']))),
            'note':'Not a like-for-like optical share: modality allocation is incomplete, and Jingce\'s semiconductor basket may hold e-beam review tools'})
    t=pd.DataFrame(rows);t.to_csv(out/'step_market.csv',index=False,float_format='%.4f')

    # Markdown lookup: one row per step, latest year, with the 2023->2025 import trend and year-to-date change.
    pct=lambda v:'n/a' if v!=v else f'{v:.0%}';mm=lambda v:'n/a' if v!=v else f'{v:,.0f}'
    last=t[t['year']==YEARS[-1]].set_index('step_id');first=t[t['year']==YEARS[0]].set_index('step_id')
    lines=[]
    for s in list(smap['step_id'])+['base_die_process_control (numerator sensitivity)']:
        r=last.loc[s]
        if r['market_basis']=='none':
            lines.append(f'| `{s}` | {r["basis_label"]} | n/a | n/a | n/a | n/a | n/a | n/a | n/a | {r["note"]} |');continue
        i0=first.loc[s,'imports_usd_m'];i1=r['imports_usd_m']
        trend='n/a' if i0!=i0 or not i0 else f'{i1/i0-1:+.0%}'
        ytd_c='n/a' if r.get('imports_ytd_2025_usd_m',float('nan'))!=r.get('imports_ytd_2025_usd_m',float('nan')) else f'{r["imports_ytd_2026_usd_m"]/r["imports_ytd_2025_usd_m"]-1:+.0%}'
        rng='n/a' if r['share_min']!=r['share_min'] else f'{r["share_min"]:.0%}–{r["share_max"]:.0%}'
        we=r.get('share_with_estimates',float('nan'))
        cv=r.get('share_constant_vendors',float('nan'));cv0=first.loc[s].get('share_constant_vendors',float('nan')) if s in first.index else float('nan')
        cvs='n/a' if cv!=cv else (f'{pct(cv0)}→{pct(cv)}' if cv0==cv0 else pct(cv))
        lines.append(f'| `{s}` | {r["basis_label"]} | {mm(i1)} | {trend} | {ytd_c} | {mm(r["domestic_usd_m"])} | {pct(r["share_base"])} ({rng}) | {pct(we)} | {cvs} | {r["note"]} |')
    md=['# HBM Step Market Lookup','',
        f'> Tier 3, generated by `sme-atlas-analysis` project `hbm_step_market` against Atlas `{atlas.state["commit"][:7]}`. Provisional: every figure inherits the proposed reference tables and scenario shares.','',
        'Per HBM process step: China customs imports, domestic vendors\' revenue (Atlas layer, with the product splits and geography exceptions of `china_share_by_segment`) and the resulting domestic share, for 2025. Import trend is 2023→2025; YTD is Jan–Aug 2026 against Jan–Aug 2025.','',
        '**Read the basis column first.**',
        '- **Group-level:** the step inherits its equipment group\'s market, of which it is a sub-application (e.g. TSV etch within dry etch). The share describes the group, not the step.',
        '- **Step pool:** named customs codes against named domestic vendors. Both sides mix in tools from outside the step (noted), so the ratio is context, not a bound: its net error has no known sign unless the note gives one.',
        '- **No separable market:** no customs code isolates the tool and no domestic revenue line exists.','',
        '| Step | Basis | Imports 2025 (USD m) | Imports 2023→25 | YTD 2026 | Domestic 2025 (USD m) | Domestic share 2025 (range) | With estimates | Constant vendors 2023→25 | Note |','|---|---|---|---|---|---|---|---|---|---|',*lines,'',
        '"Constant vendors" restricts the Atlas numerator to vendors reported in all three years, so a vendor entering the data does not read as localisation; it excludes the estimate layer.','',
        '"With estimates" adds the unlisted-vendor estimate layer (SMEE, SiCarrier, CETC units, long tail; tiers D–E) for group-level rows, matching the headline figures in `china_share_by_segment`.','',
        'Full series with low/base/high for 2023–25, domestic vendors and held-out revenue are in `step_market.csv`.']
    (out/'step_lookup.md').write_text('\n'.join(md)+'\n')
    manifest.write(out,'hbm_step_market',[atlas],['A-FX-CNY-USD','A-CMP-IN-84862090','A-CLEAN-IN-84862090','A-BACKEND-IN-84862090','A-WAFER-HANDLING-IN-84864039','A-GEO-ALL-AS-CHINA','A-NAURA-LINE-GROWTH','A-KINGSEMI-H2-IN-NAURA'],
                   'Step-level market lookup; Atlas layer with product splits and geography exceptions; estimate layer excluded.')
    return {'steps':int(smap.shape[0]),'rows':len(t)}
