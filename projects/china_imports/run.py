"""Settled China equipment-import figures by group, origin and province (customs, allocated per reference tables)."""
import pandas as pd
from sme_analysis import manifest, reference
from sme_analysis.cli import project_module
from sme_analysis.data import num

YEARS = [2021, 2022, 2023, 2024, 2025]
YTD_YEARS = [2025, 2026]
ORDER = ['litho','deposition','dry_etch','process_control','cleaning_strip','cmp','doping','thermal','track_automation_other',
         'backend','test','mask_making','wafer_making','handling_unallocated']
ASSUMPTIONS = ['A-CMP-IN-84862090','A-CLEAN-IN-84862090','A-BACKEND-IN-84862090','A-WAFER-HANDLING-IN-84864039']

def allocations(atlas):
    share=project_module('china_share_by_segment');months,label=share.ytd_window(atlas)
    d_full,_=share.imports_by_group(atlas,years=YEARS)
    d_ytd,_=share.imports_by_group(atlas,years=YTD_YEARS,months=months)
    d_full['period']=d_full['year'].astype(str);d_ytd['period']=d_ytd['year'].astype(str)+' '+label
    return pd.concat([d_full,d_ytd],ignore_index=True)

def mix(atlas, detail, dim, names):
    """Share of each group's covered value by origin or province.

    Each allocation row takes the mix of its own source (the code, filtered by any origin rule), weighted by the
    row's share of that source's pool; coverage is the filtered table's share of the group's value.
    """
    pp=atlas.statistics('china_customs/imports_hs8_partner_province_monthly.csv');pp['usd']=num(pp['usd'])
    pp['year']=pp['period'].str[:4].astype(int);pp['month']=pp['period'].str[5:7].astype(int)
    rows=[];base=detail[detail['case']=='base'];months,label=project_module('china_share_by_segment').ytd_window(atlas)
    for period,grp in base.groupby('period'):
        y=int(period[:4]);sub=pp[(pp['year']==y)&(pp['month'].isin(months) if label in period else True)]
        pools=grp.groupby(['hs8','origin_rule'])['usd'].sum()
        for g,gg in grp.groupby('group_id'):
            acc={};covered=0.0;total=gg['usd'].sum()
            for (hs8,rule),alloc in gg.groupby(['hs8','origin_rule'])['usd'].sum().items():
                src=sub[sub['hs8']==hs8];kind,_,code=rule.partition(':')
                if kind=='exclude':src=src[src['partner_code']!=code]
                elif kind=='only':src=src[src['partner_code']==code]
                if not len(src) or not pools[(hs8,rule)]:continue
                frac=alloc/pools[(hs8,rule)]
                for k,v in src.groupby(dim)['usd'].sum().items():acc[k]=acc.get(k,0)+v*frac
                covered+=src['usd'].sum()*frac
            for k,v in acc.items():
                rows.append({'period':period,'group_id':g,dim:k,'name':names.get(k,k),'share_of_covered':v/covered if covered else float('nan'),
                             'coverage':covered/total if total else float('nan')})
    return pd.DataFrame(rows)

def run(atlas, out, preview=None):
    seg=reference.load('segments');wfe=dict(zip(seg['group_id'],seg['wfe']))
    detail=allocations(atlas)
    g=detail.pivot_table(index=['period','group_id'],columns='case',values='usd',aggfunc='sum').reset_index()
    g=g.rename(columns={'low':'usd_m_low','base':'usd_m_base','high':'usd_m_high'})
    for c in ('usd_m_low','usd_m_base','usd_m_high'):g[c]=g[c]/1e6
    g['usd_m_min']=g[['usd_m_low','usd_m_base','usd_m_high']].min(axis=1);g['usd_m_max']=g[['usd_m_low','usd_m_base','usd_m_high']].max(axis=1)
    g['wfe']=g['group_id'].map(wfe);g['order']=g['group_id'].map({k:i for i,k in enumerate(ORDER)})
    g=g.sort_values(['period','order']).drop(columns='order')
    g.to_csv(out/'imports_by_group.csv',index=False,float_format='%.1f')
    codes=detail[detail['case']=='base'].groupby(['period','hs8']).agg(usd_m=('usd','sum'),groups=('group_id',lambda s:';'.join(sorted(set(s))))).reset_index()
    codes['usd_m']=codes['usd_m']/1e6;codes.to_csv(out/'imports_by_code.csv',index=False,float_format='%.1f')
    P=dict(zip(*[atlas.statistics('china_customs/partners.csv')[c] for c in ('partner_code','name_en')]))
    V=dict(zip(*[atlas.statistics('china_customs/provinces.csv')[c] for c in ('province_code','name_en')]))
    om=mix(atlas,detail,'partner_code',P);pm=mix(atlas,detail,'province_code',{k:v.replace(' Province','') for k,v in V.items()})
    om.to_csv(out/'origin_mix.csv',index=False,float_format='%.4f');pm.to_csv(out/'province_mix.csv',index=False,float_format='%.4f')
    # Summary
    m=lambda v:'n/a' if v!=v else f'{v:,.0f}';pct=lambda v:'n/a' if v!=v else f'{v:.0%}'
    _,label=project_module('china_share_by_segment').ytd_window(atlas);per=[str(y) for y in YEARS]+[f'{y} {label}' for y in YTD_YEARS]
    def table(groups):
        lines=['| group | '+' | '.join(per)+' | 2026 YTD vs 2025 YTD |','|---|'+'---|'*(len(per)+1)]
        for grp in groups:
            r=g[g['group_id']==grp].set_index('period')
            cell=lambda p:(m(r.loc[p,'usd_m_base'])+(f' ({m(r.loc[p,"usd_m_min"])}–{m(r.loc[p,"usd_m_max"])})' if r.loc[p,'usd_m_max']-r.loc[p,'usd_m_min']>0.5 else '')) if p in r.index else 'n/a'
            yoy=r.loc[per[-1],'usd_m_base']/r.loc[per[-2],'usd_m_base']-1 if {per[-1],per[-2]}<=set(r.index) else float('nan')
            lines.append(f'| {grp} | '+' | '.join(cell(p) for p in per)+f' | {"n/a" if yoy!=yoy else f"{yoy:+.0%}"} |')
        return '\n'.join(lines)
    tot=g.groupby(['period','wfe'])['usd_m_base'].sum().unstack()
    top=lambda mixdf,grp,period,k=3:', '.join(f'{r.name_} {r.share_of_covered:.0%}' for r in mixdf[(mixdf['group_id']==grp)&(mixdf['period']==period)].rename(columns={'name':'name_'}).sort_values('share_of_covered',ascending=False).head(k).itertuples())
    mixlines=['| group | top origins (2025) | top provinces (2025) | coverage |','|---|---|---|---|']
    for grp in ORDER:
        c=om[(om['group_id']==grp)&(om['period']=='2025')]['coverage']
        if len(c):mixlines.append(f'| {grp} | {top(om,grp,"2025")} | {top(pm,grp,"2025")} | {pct(c.iloc[0])} |')
    wfe_groups=[x for x in ORDER if wfe.get(x)=='yes'];other=[x for x in ORDER if wfe.get(x)=='no']
    summary=['# China Equipment Imports by Segment','',
      f'> Tier 3, generated by `sme-atlas-analysis` project `china_imports` against Atlas `{atlas.state["commit"][:7]}`. Customs values (USD m, base case with low–high where a scenario applies). Classification evidence: `docs/customs_code_evidence.md`.','',
      '**Method.** China customs imports (all origins) are allocated to equipment groups by `reference/customs_segment_map.csv`. Mixed codes are split by proposed scenario shares: CMP, wet cleaning and back-end tools inside 84862090, and fab automation inside 84864039. Jan–Aug columns compare like-for-like months; fixed annual amounts are scaled to 8/12.','',
      '## Wafer-fab equipment groups','',table(wfe_groups),'',
      '## Other groups (outside the WFE share chart)','',table(other),'',
      '## Totals (base)','','| period | WFE | other |','|---|---|---|',
      *[f'| {p} | {m(tot.loc[p,"yes"])} | {m(tot.loc[p,"no"])} |' for p in per if p in tot.index],'',
      '## Origin and importer-province mix','',
      'These are shares of the value covered by the filtered table (8 origins × 14 provinces), with each code\'s mix weighted by its allocation to the group. Origin is country of origin, not vendor nationality. Province is the importer\'s registered location, not necessarily the fab site.','',
      *mixlines,'',
      '## Caveats','',
      '- **Scenario shares are proposed, not measured.** Wet cleaning and back-end inside 84862090 rest on declaration examples and unit values, and have no vendor-side value anchor yet. `track_automation_other` is the residual, so it moves inversely with them.',
      '- **Test is a floor.** 90308200 holds ATE, handlers and probers, but some test equipment is declared as parts or under 90318090.',
      '- **Not separable at 8 digits.** E-beam inspection/CD-SEM (90121000/90318090) and X-ray inspection (90221990) are not included. Process control is optical only (90314100).',
      '- **Back-end is partial.** It covers the 8486.40 assembly codes, part of 84862090 and the laser marking/dicing carve-outs above. Back-grinders and dicing saws declared under 84861020/84861030 stay in `wafer_making` because those codes also hold ingot and wafer tools.']
    (out/'summary.md').write_text('\n'.join(summary)+'\n')
    manifest.write(out,'china_imports',[atlas],['A-FX-CNY-USD']+ASSUMPTIONS,'Customs imports allocated by the reference tables; scenario shares proposed.')
    return {'periods':per,'groups':sorted(set(g['group_id']))}
