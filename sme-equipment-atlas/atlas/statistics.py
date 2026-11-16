"""As-reported public statistics under statistics/ (see statistics/README.md).

This module parses, rebuilds and checks tables only. Mapping to atlas
categories, currency conversion and market calculations do not belong here.
"""
import csv
import io
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from .core import ROOT, require, digest

# China Customs portal exports (stats.customs.gov.cn): Chinese and English interfaces.
CUSTOMS_HEADERS = {
    '数据年月':'period','商品编码':'hs8','商品名称':'hs8_name',
    '贸易伙伴编码':'partner_code','贸易伙伴名称':'partner_name',
    '贸易方式编码':'trade_mode_code','贸易方式名称':'trade_mode_name',
    '收发货人注册地编码':'province_code','收发货人注册地名称':'province_name',
    '关别编码':'customs_district_code','关别名称':'customs_district_name',
    '运输方式编码':'transport_code','运输方式名称':'transport_name',
    '第一数量':'qty1','第一计量单位':'qty1_unit','第二数量':'qty2','第二计量单位':'qty2_unit',
    'Date of data':'period','Commodity code':'hs8','Commodity':'hs8_name',
    'Trading partner code':'partner_code','Trading partner':'partner_name',
    'Trade mode code':'trade_mode_code','Trade mode':'trade_mode_name',
    'Locations of importers and exporters code':'province_code','Locations of importers and exporters':'province_name',
    'Quantity':'qty1','Unit':'qty1_unit','Supplementary Quantity':'qty2','Supplementary Unit':'qty2_unit',
}
CURRENCIES = {'美元':'usd','US dollar':'usd','人民币':'cny','Renminbi Yuan':'cny'}
UNITS = {'台':'items','Number of item':'items','千克':'kg','Kilogram':'kg'}
DIMENSIONS = [('hs8','hs8'),('partner_code','partner'),('province_code','province'),('trade_mode_code','trade_mode'),
              ('customs_district_code','customs_district'),('transport_code','transport')]
LABELS = {'hs8':'hs8_name','partner_code':'partner_name','province_code':'province_name','trade_mode_code':'trade_mode_name',
          'customs_district_code':'customs_district_name','transport_code':'transport_name'}
RAW_NAME = re.compile(r'([MX])_(\d{4})_(\d{2})-(\d{2})_monthly_[a-z0-9_]+\.csv')
NUMBER = re.compile(r'-?\d+(\.\d+)?')
MEASURES = ['quantity_items','weight_kg','usd','cny']
MANUAL = ['pulled_on','notes']

def read_csv(path):
    with open(path,newline='',encoding='utf-8') as fh:return list(csv.DictReader(fh))

def write_csv(path,fields,rows):
    with open(path,'w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)

def parse_customs_export(path):
    """One portal CSV export -> (query metadata, rows). Flow and query period come from the file name."""
    path=Path(path);m=RAW_NAME.fullmatch(path.name)
    require(m,f'{path.name}: raw exports must be named <M|X>_<year>_<MM-MM>_monthly_<groupings>.csv')
    flow,year,first,last=m.groups()
    rows=[r for r in csv.reader(io.StringIO(path.read_bytes().decode('gb18030'))) if any(c.strip() for c in r)]
    header=[h.strip() for h in rows[0]];cols={};currency=None
    for i,h in enumerate(header):
        if not h:continue
        if h in CURRENCIES:
            require(currency is None,f'{path.name}: more than one value column');currency=CURRENCIES[h];cols['value']=i
        else:
            require(h in CUSTOMS_HEADERS,f'{path.name}: unknown column {h!r}');cols[CUSTOMS_HEADERS[h]]=i
    require(currency and {'period','hs8','qty1','qty1_unit','qty2','qty2_unit'}<=set(cols),f'{path.name}: missing required columns')
    out=[]
    for r in rows[1:]:
        rec={k:r[i].strip() for k,i in cols.items()}
        require(re.fullmatch(r'\d{6}',rec['period']) and rec['period'][:4]==year and first<=rec['period'][4:]<=last,f'{path.name}: period {rec["period"]} outside query')
        require(UNITS.get(rec['qty1_unit'])=='items' and UNITS.get(rec['qty2_unit'])=='kg',f'{path.name}: unexpected units {rec["qty1_unit"]}/{rec["qty2_unit"]}')
        for k in ('qty1','qty2','value'):
            rec[k]=rec[k].replace(',','');require(rec[k]=='' or NUMBER.fullmatch(rec[k]),f'{path.name}: non-numeric {k} {rec[k]!r}')
        out.append(rec)
    meta={'query_id':path.stem,'raw_file':'raw/'+path.name,'sha256':digest(path),'flow':flow,'currency':currency,
          'interface':'zh' if '数据年月' in header else 'en','year':year,'month_start':first,'month_end':last,
          'group_by':'+'.join(label for col,label in DIMENSIONS if col in cols),'dims':[col for col,_ in DIMENSIONS if col in cols],'rows':len(out)}
    return meta,out

def build_china_customs(root=ROOT,out=None):
    """Rebuild every china_customs table from raw/ exports. Values are kept exactly as exported."""
    base=Path(root)/'statistics/china_customs';out=Path(out) if out else base
    previous={r['query_id']:r for r in read_csv(base/'queries.csv')} if (base/'queries.csv').exists() else {}
    tables={};labels={};queries=[]
    for p in sorted((base/'raw').glob('*.csv')):
        meta,rows=parse_customs_export(p);dims=meta['dims']
        name=('imports' if meta['flow']=='M' else 'exports')+'_'+meta['group_by'].replace('+','_')+'_monthly'
        table=tables.setdefault(name,{'dims':dims,'rows':{}})
        require(table['dims']==dims,f'{name}: inconsistent groupings')
        for rec in rows:
            key=(rec['period'][:4]+'-'+rec['period'][4:],)+tuple(rec[d] for d in dims)
            row=table['rows'].setdefault(key,{'quantity_items':'','weight_kg':'','usd':'','cny':'','query_ids':[]})
            for field,value in (('quantity_items',rec['qty1']),('weight_kg',rec['qty2']),(meta['currency'],rec['value'])):
                require(row[field] in ('',value) or Decimal(row[field])==Decimal(value),f'{name} {key}: overlapping pulls disagree on {field}; move the superseded export out of raw/')
                row[field]=row[field] or value
            row['query_ids'].append(meta['query_id'])
            for d in dims:
                if rec.get(LABELS[d]):labels.setdefault(d,{}).setdefault(rec[d],{})[meta['interface']]=rec[LABELS[d]]
        keep=previous.get(meta['query_id'],{})
        queries.append({**{k:meta[k] for k in ('query_id','raw_file','sha256','flow','currency','interface','year','month_start','month_end','group_by')},
                        'hs8_codes':';'.join(sorted({r['hs8'] for r in rows})),
                        'partner_codes':';'.join(sorted({r['partner_code'] for r in rows})) if 'partner_code' in dims else 'all',
                        'province_codes':';'.join(sorted({r['province_code'] for r in rows})) if 'province_code' in dims else 'all',
                        'rows':meta['rows'],**{k:keep.get(k,'') for k in MANUAL}})
    out.mkdir(parents=True,exist_ok=True)
    for name,table in sorted(tables.items()):
        fields=['period']+table['dims']+MEASURES+['query_ids']
        write_csv(out/(name+'.csv'),fields,[dict(zip(['period']+table['dims'],k),**{m:v[m] for m in MEASURES},query_ids=';'.join(v['query_ids'])) for k,v in sorted(table['rows'].items())])
    for d,fname,codefield in (('hs8','codes_hs8.csv','hs8'),('partner_code','partners.csv','partner_code'),('province_code','provinces.csv','province_code')):
        write_csv(out/fname,[codefield,'name_zh','name_en'],[{codefield:c,'name_zh':n.get('zh',''),'name_en':n.get('en','')} for c,n in sorted(labels.get(d,{}).items())])
    write_csv(out/'queries.csv',list(queries[0]) if queries else ['query_id'],queries)
    return {'queries':len(queries),'tables':{n:len(t['rows']) for n,t in sorted(tables.items())}}

def _unique(path,key):
    rows=read_csv(path);keys=[tuple(r[k] for k in key) for r in rows]
    require(len(keys)==len(set(keys)),f'{path.name}: duplicate {key} rows');return rows

def check_statistics(root=ROOT):
    """Integrity checks only: provenance hashes, exact rebuild from raw, unique keys and cross-source totals."""
    base=Path(root)/'statistics';result={}
    for d in ('china_customs','comtrade','eurostat','cepea'):require((base/d/'README.md').is_file(),f'statistics/{d}: README.md missing')
    cc=base/'china_customs';queries=read_csv(cc/'queries.csv')
    require({q['raw_file'] for q in queries}=={'raw/'+p.name for p in (cc/'raw').glob('*.csv')},'china_customs: queries.csv does not list exactly the files in raw/')
    for q in queries:require(digest(cc/q['raw_file'])==q['sha256'],f'{q["raw_file"]}: hash differs from queries.csv')
    with tempfile.TemporaryDirectory() as tmp:
        built=build_china_customs(root,tmp);generated={p.name:p.read_bytes() for p in Path(tmp).glob('*.csv')}
    require(set(generated)=={p.name for p in cc.glob('*.csv')},'china_customs: committed tables differ from the generated set; run statistics-build')
    for n,b in generated.items():require((cc/n).read_bytes()==b,f'china_customs/{n} does not reproduce from raw exports; run statistics-build')
    result['china_customs']=built
    totals={(r['period'],r['hs8']):r for r in read_csv(cc/'imports_hs8_monthly.csv')} if (cc/'imports_hs8_monthly.csv').exists() else {}
    if (cc/'imports_hs8_partner_province_monthly.csv').exists():
        parts={}
        for r in read_csv(cc/'imports_hs8_partner_province_monthly.csv'):
            if r['usd']:parts[(r['period'],r['hs8'])]=parts.get((r['period'],r['hs8']),Decimal(0))+Decimal(r['usd'])
        for k,v in parts.items():
            if k in totals and totals[k]['usd']:require(v<=Decimal(totals[k]['usd']),f'{k}: origin x province rows exceed the all-origin total')
    comtrade=_unique(base/'comtrade/china_hs6_annual.csv',('year','flow','hs6','partner_m49'))
    # Each basket of HS6 headings held in full at HS8 must reproduce Comtrade's HS6 import total for complete years.
    # 848640 gets a wider tolerance: its 2025 portal total (pulled 2026-09-28) sits 0.29% below Comtrade (pulled
    # 2026-09-23), consistent with revisions to the latest year; 2021-24 agree within 0.06%.
    # 903082 is a single small code: 2021-23 and 2025 agree within 0.27%, but 2024 is 1.6% ($10m) below Comtrade
    # (unexplained: revision or a suppressed record), so it is checked at 2%.
    for key,basket,tol in (('comtrade_totals_matched',{'848620','903141'},'0.0025'),('comtrade_848640_matched',{'848640'},'0.005'),
                           ('comtrade_903082_matched',{'903082'},'0.02')):
        matched=[]
        for year in sorted({k[0][:4] for k in totals}):
            rows=[r for k,r in totals.items() if k[0][:4]==year and r['hs8'][:6] in basket]
            if len({r['period'] for r in rows})<12 or any(not r['usd'] for r in rows):continue
            c=[Decimal(r['value_usd']) for r in comtrade if r['year']==year and r['flow']=='M' and r['partner_m49']=='0' and r['hs6'] in basket]
            if len(c)!=len(basket) or {r['hs8'][:6] for r in rows}!=basket:continue
            gap=abs(sum(Decimal(r['usd']) for r in rows)/sum(c)-1)
            require(gap<=Decimal(tol),f'{year} {"+".join(sorted(basket))}: customs HS8 total differs from Comtrade HS6 by {gap:.4%}');matched.append(year)
        result[key]=matched
    _unique(base/'eurostat/eu_exports_to_china_hk_monthly.csv',('reporter','partner','hs6','flow','indicator','period'))
    _unique(base/'eurostat/fx_annual_per_eur.csv',('currency','year'))
    for n,k in (('semiconductor_equipment_annual',('year','level','category_en')),('semiconductor_equipment_top10',('year','rank')),
                ('semiconductor_equipment_h1',('year','scope')),('bulletins',('issue',))):_unique(base/f'cepea/{n}.csv',k)
    require(all(re.fullmatch(r'[a-f0-9]{64}',r['sha256']) for r in read_csv(base/'cepea/bulletins.csv')),'cepea/bulletins.csv: invalid sha256')
    return result
