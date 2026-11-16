"""Portable evidence validation, named series and conservative reconciliation.

Standard library only. Original assets and full-text indexes live in local/;
they are not needed for structural CI checks and are not uploaded to GitHub.
"""
import csv
import hashlib
import io
import json
import re
import subprocess
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = ('geography', 'geography_basis', 'revenue_basis', 'price_basis',
              'equipment_condition', 'service_scope', 'tax_basis')
RELATIONS = {'eq', 'gt', 'ge', 'lt', 'le', 'approx', 'approaching', 'range'}
# Values are recorded in the currency the issuer printed and are never converted. A reconciliation
# whose two sides differ in currency is blocked unless its recipe declares an explicit FX adjustment,
# so widening this map adds comparators without letting an exchange rate in by the back door.
MONETARY = {'CNY': Decimal(1), 'CNY_10k': Decimal(10000), 'CNY_100m': Decimal(100000000),
            'CNY_million': Decimal(1000000), 'USD': Decimal(1), 'USD_million': Decimal(1000000),
            'JPY': Decimal(1), 'JPY_million': Decimal(1000000), 'JPY_100m': Decimal(100000000),
            'EUR': Decimal(1), 'EUR_thousand': Decimal(1000), 'EUR_million': Decimal(1000000),
            'KRW': Decimal(1), 'KRW_million': Decimal(1000000), 'KRW_100m': Decimal(100000000),
            'HKD': Decimal(1), 'HKD_thousand': Decimal(1000), 'HKD_million': Decimal(1000000),
            'JPY_thousand': Decimal(1000), 'KRW_thousand': Decimal(1000), 'HKD_100m': Decimal(100000000)}

class ValidationError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ValidationError(message)

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def number(value):
    try:
        n = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(f'Invalid number: {value}') from exc
    require(n.is_finite(), 'Nonfinite numeric value')
    return n

def index(rows, key):
    out = {}
    for r in rows:
        require(r[key] not in out, f'Duplicate {key}: {r[key]}')
        out[r[key]] = r
    return out

def valid_date(value, partial=False):
    if partial and re.fullmatch(r'\d{4}(-\d{2})?', value):
        date.fromisoformat(value + ('-01-01' if len(value) == 4 else '-01'))
    else:
        date.fromisoformat(value)

def load(root=ROOT):
    d = root / 'data'
    from .registry import read_records
    return {
        'schema': read_json(d/'schema.json'),
        'datasets': index(read_records('datasets',root), 'dataset_id'),
        'sources': index(read_records('sources',root), 'source_id'),
        'entities': index(read_records('entities',root), 'entity_id'),
        'categories': index(read_records('categories',root), 'category_id'),
        'platforms': index(read_records('platforms',root), 'platform_id'),
        'scopes': index(read_records('reporting_scopes',root), 'reporting_scope_id'),
        'metrics': index(read_records('metrics',root), 'metric_id'),
        'observations': index(read_records('observations',root), 'observation_id'),
        'series': read_records('series',root),
        'reconciliations': read_records('reconciliations',root),
        'coverage': read_records('coverage',root),
    }

def validate_observation(o, data):
    oid = o.get('observation_id', '<missing id>')
    from .schema import validate_shape, registry_constraints
    schema=data['schema']
    validate_shape(o,schema,require,oid)
    registry_constraints(o,data,schema,require)
    from .schema import validate_node_fields
    validate_node_fields(o['dimensions'],o['evidence'],schema,require,oid+'.node',measurement_scope=data['scopes'].get(o['reporting_scope_id'],{}))
    require(re.fullmatch(r'[A-Za-z0-9_-]+', oid), f'{oid}: unsafe ID')
    for field, table in [('dataset_id','datasets'), ('source_id','sources'), ('entity_id','entities'),
                         ('category_id','categories'), ('reporting_scope_id','scopes'), ('metric_id','metrics')]:
        require(o[field] in data[table], f'{oid}: unknown {field}')
    dataset = data['datasets'][o['dataset_id']]
    source = data['sources'][o['source_id']]
    require(data['scopes'][o['reporting_scope_id']]['category_id']==o['category_id'],f'{oid}: reporting scope/category mismatch')
    if o['dimensions'].get('counterparty_bucket')=='named_not_ranked':
        # Otherwise the bucket becomes a dumping ground for rows whose position is simply unknown.
        require(o['dimensions'].get('reported_counterparty_name'),
                f'{oid}: named_not_ranked requires reported_counterparty_name')
    if 'denominator_scope_id' in o['dimensions']:
        require(o['dimensions']['denominator_scope_id'] in data['scopes'],
                f'{oid}: unknown denominator reporting scope')
    require(source['dataset_id'] == o['dataset_id'], f'{oid}: source/dataset mismatch')
    # 'reference_only' is a deliberate third tier: third-party context recorded alongside evidence but
    # never treated as verified. Its segregation is enforced in reconcile(), which refuses such rows as
    # computation inputs unless a recipe explicitly approves them and states why the boundaries match.
    require(dataset['status'] in {'available','reference_only'}, f'{oid}: dataset is not available')
    require(dataset['git_values_allowed'] is True, f'{oid}: dataset values not approved for repository')
    require(o['claim_kind'] in {'company_reported','analyst_estimate','reported_market_statistic'}, f'{oid}: invalid claim kind')
    require(dataset['kind'] != 'analyst_market_data' or o['claim_kind']=='analyst_estimate', f'{oid}: analyst estimates cannot be relabelled company facts')
    if o['platform_id']:
        p = data['platforms'].get(o['platform_id'])
        require(p and p['entity_id']==o['entity_id'] and p['category_id']==o['category_id'], f'{oid}: platform identity mismatch')
    metric = data['metrics'][o['metric_id']]
    from .schema import unbounded_percent_metric
    unbounded_percent=unbounded_percent_metric(metric,schema,require)
    value = number(o['value'])
    require(metric.get('allow_negative') is True or value >= 0, f'{oid}: negative observation')
    if o['relation']=='range':
        require('upper_value' in o and number(o['upper_value'])>=value, f'{oid}: invalid range')
    if o['unit']==schema['x-atlas-percent-semantics']['unit'] and not unbounded_percent:
        require(number(o.get('upper_value',o['value']))<=number(schema['x-atlas-percent-semantics']['default_maximum']), f'{oid}: share exceeds 100%')
    period = o['period']
    valid_date(period['end'])
    if period['basis'] in {'flow','stock_change','period_status'}:
        require(period['kind']!='as_of' and period.get('start'), f'{oid}: interval measure requires start')
        valid_date(period['start'])
        require(period['start']<=period['end'], f'{oid}: reversed dates')
        days=(date.fromisoformat(period['end'])-date.fromisoformat(period['start'])).days+1
        if period['kind']=='annual':
            require(days in {364,365,366,371}, f'{oid}: annual period must span a calendar or 52/53-week fiscal year')
        if period['kind']=='multi_year':
            require(days>371, f'{oid}: multi-year period must exceed a full fiscal year')
        if period['kind']=='quarter':
            require(days in {89,90,91,92,98}, f'{oid}: quarter must span three calendar months or 13/14 fiscal weeks')
    else:
        require(period['kind']=='as_of' and not period.get('start'), f'{oid}: stock/cumulative uses as-of date')
    require(set(DIMENSIONS)<=o['dimensions'].keys(), f'{oid}: missing dimension metadata')
    require(all(isinstance(o['dimensions'][k],str) and o['dimensions'][k].strip() for k in DIMENSIONS),f'{oid}: dimensions must be nonempty strings; use unknown explicitly')
    e = o['evidence']
    require(e['status'] in {'pending','source_checked','rejected'}, f'{oid}: invalid evidence status')
    require(int(e['page'])>0 and e['original_label'], f'{oid}: missing source locator')
    require(e.get('excerpt') and e.get('reviewer') and e.get('review_date') if e['status']=='source_checked' else True,
            f'{oid}: checked evidence requires excerpt and reviewer')
    if e.get('review_date'):
        valid_date(e['review_date'])
        require(date.fromisoformat(e['review_date'])<=date.today(), f'{oid}: future review date')
    if e.get('qualifier_review'):
        require(date.fromisoformat(e['qualifier_review']['review_date'])<=date.today(), f'{oid}: future qualifier review date')
    if o.get('conversion_audit'):
        audit=o['conversion_audit']
        require(o['unit']=='CNY' and number(audit['conversion_factor_to_CNY'])==10000,f'{oid}: invalid native monetary conversion')
        converted=number(audit['native_value'])*10000
        require(converted==number(audit['converted_value_CNY'])==value,f'{oid}: conversion arithmetic differs from stored value')
    from .evidence import validate_numeric_evidence
    validate_numeric_evidence(o,data,require,number)
    if o['metric_id'] in {'market_size','reported_market_share'}:
        require(o.get('market_definition_id') in dataset.get('market_definitions',{}), f'{oid}: market definition missing')
        md=dataset['market_definitions'][o['market_definition_id']]
        require(all(md.get(k) for k in ('native_category','category_id','population','methodology','category_mapping_rationale')),f'{oid}: incomplete market definition')
        require(md['category_id']==o['category_id'],f'{oid}: market category mapping mismatch')
        require(md.get('dimensions')==o['dimensions'],f'{oid}: market-definition dimensions disagree with observation')
    coincident=o.get('coincident_value')
    if coincident:
        # A declaration only resolves a real coincidence: the rows must agree on the fact
        # (entity, metric, unit, value, period) within one filing, and must not be the same row.
        # Which row an aggregation keeps is fixed by basis, not by which one carries the field.
        other=data['observations'].get(coincident['counterpart_observation_id'])
        require(other is not None and other['observation_id']!=oid,f'{oid}: invalid coincident counterpart')
        for k in ('entity_id','metric_id','unit','value','source_id'):
            require(o[k]==other[k],f'{oid}: coincident counterpart differs in {k}')
        require(o['period']==other['period'],f'{oid}: coincident counterpart differs in period')
        require(not other.get('coincident_value'),f'{oid}: coincident counterpart carries its own declaration; point every row of a set at one counterpart')
    if o['revision_of']:
        old = data['observations'].get(o['revision_of'])
        require(old is not None and old['observation_id']!=oid, f'{oid}: invalid revision target')
        for k in ('entity_id','category_id','reporting_scope_id','platform_id','metric_id','unit','period','dimensions'):
            require(o[k]==old[k], f'{oid}: revision changes {k}; create a distinct observation')

def validate(data, root=None):
    from .entities import entity_ancestors
    entity_ancestors(data['entities'])
    from .schema import validate_shape
    for scope in data['scopes'].values():
        if 'node_scope' in scope:
            validate_shape(scope['node_scope'],data['schema']['$defs']['process_node_fields'],require,scope['reporting_scope_id']+'.node_scope',document=data['schema'])
    for group in ('entities','platforms'):
        for record in data[group].values():
            if record.get('evidence'):
                evidence=record['evidence']
                from .schema import validate_node_fields
                validate_node_fields(evidence,evidence,data['schema'],require,group+'.evidence.node')
                source=data['sources'].get(evidence.get('source_id'))
                require(source is not None,'Unknown evidence source')
                dataset=data['datasets'].get(source['dataset_id'])
                require(dataset and dataset.get('git_values_allowed') is True,'Evidence excerpts not approved for repository')
                if evidence.get('review_date'):valid_date(evidence['review_date'])
    for c in data['categories'].values():
        require(not c.get('parent_category_id') or c['parent_category_id'] in data['categories'],'Unknown parent category')
        seen=set();node=c
        while node.get('parent_category_id'):
            cid=node['category_id']
            require(cid not in seen,'Category parent cycle')
            seen.add(cid);node=data['categories'][node['parent_category_id']]
    for p in data['platforms'].values():
        require(p['entity_id'] in data['entities'] and p['category_id'] in data['categories'],'Unknown platform entity/category')
        if p.get('evidence'):
            e=p['evidence'];require(e['source_id'] in data['sources'] and int(e['page'])>0 and e.get('excerpt'),'Platform needs source passage')
            require(e['status'] in {'pending','source_checked'},'Invalid platform review')
            require(e['status']!='source_checked' or (e.get('reviewer') and e.get('review_date')),'Platform review provenance missing')
            if e.get('review_date'):valid_date(e['review_date'])
        for h in p.get('maturity_history',[]):
            from .schema import validate_node_fields
            validate_node_fields(h,h,data['schema'],require,p['platform_id']+'.maturity.node')
            needed={'source_id','page','excerpt','status','reviewer','review_date','reported_maturity','as_of','claim_kind','notes'}
            require(needed<=h.keys(),'Platform maturity history missing fields')
            source=data['sources'].get(h['source_id'])
            require(source is not None,'Unknown platform maturity source')
            dataset=data['datasets'].get(source['dataset_id'])
            require(dataset and dataset.get('git_values_allowed') is True,'Platform maturity excerpt not approved for repository')
            require(int(h['page'])>0 and h['excerpt'] and h['reported_maturity'],'Platform maturity needs stage and source passage')
            require(h['status'] in {'pending','source_checked'},'Invalid platform maturity review')
            require(h['claim_kind']=='company_reported','Platform maturity must remain a company-reported claim')
            date_rules=data['schema']['x-atlas-platform-maturity-date']
            date_basis=h.get('date_basis',date_rules['legacy_default'])
            require(date_basis in date_rules['allowed_bases'],'Invalid platform maturity date basis')
            if date_basis==date_rules['undated_basis']:
                require(h['as_of']=='','Report-context maturity must not assign an as-of date')
            else:
                valid_date(h['as_of'])
            require(h['status']!='source_checked' or (h['reviewer'] and h['review_date']),'Platform maturity review provenance missing')
            if h['review_date']:valid_date(h['review_date'])
    for s in data['sources'].values():
        require(s['dataset_id'] in data['datasets'], 'Source dataset missing')
        require(re.fullmatch(r'[a-f0-9]{64}',s['sha256']), 'Invalid source hash')
        if s.get('publication_date'): valid_date(s['publication_date'], partial=True)
    from .schema import unbounded_percent_metric,source_decrease_metric,source_loss_metric
    for metric in data['metrics'].values():
        unbounded_percent_metric(metric,data['schema'],require)
        source_decrease_metric(metric,data['schema'],require)
        source_loss_metric(metric,data['schema'],require)
    for o in data['observations'].values(): validate_observation(o,data)
    # Detect cycles rather than relying on order of observations.
    for o in data['observations'].values():
        seen=set(); node=o
        while node['revision_of']:
            require(node['observation_id'] not in seen, 'Revision cycle')
            seen.add(node['observation_id']);node=data['observations'][node['revision_of']]
    for s in data['series']:
        require(s['mode'] in {'comparable','evidence_collection'},f"{s['series_id']}: invalid series mode")
        require(len(s['observation_ids'])==len(set(s['observation_ids'])), f"{s['series_id']}: duplicate input")
        for oid in s['observation_ids']:
            require(oid in data['observations'], f"{s['series_id']}: unknown input {oid}")
            require(data['observations'][oid]['evidence']['status']=='source_checked', 'Series contains unreviewed evidence')
        if s['mode']=='comparable':
            rows=[data['observations'][i] for i in s['observation_ids']]
            def comparable(o):
                return tuple(o[k] for k in ('entity_id','category_id','reporting_scope_id','platform_id','metric_id','unit')) + (o['period']['basis'],o['period']['kind'],json.dumps(o['dimensions'],sort_keys=True))
            require(len({comparable(o) for o in rows})<=1, f"{s['series_id']}: incompatible observations")
            dates=[(o['period'].get('start'),o['period']['end']) for o in rows]
            require(len(dates)==len(set(dates)), f"{s['series_id']}: duplicate selected period")
            if rows and rows[0]['period']['kind'] in {'interim','multi_year'}:
                lengths=[(date.fromisoformat(o['period']['end'])-date.fromisoformat(o['period']['start'])).days for o in rows]
                require(max(lengths)-min(lengths)<=7,f"{s['series_id']}: incompatible interval durations")
    index(data['series'],'series_id');index(data['reconciliations'],'reconciliation_id');index(data['coverage'],'coverage_id')
    for c in data['coverage']:
        require(c['status'] in {'not_searched','reviewed_found','reviewed_not_found','conflicting','unresolved'}, 'Invalid coverage status')
        require(all(s in data['sources'] for s in c['reviewed_source_ids']), 'Coverage references missing source')
        require(c['status'] not in {'reviewed_found','reviewed_not_found'} or c['reviewed_source_ids'], 'Reviewed coverage needs sources')
    if root is not None:
        from .research import validate_research
        validate_research(data,root)
        from .registry import validate_partition_owners
        validate_partition_owners(root)
    return {'structural_validation':'passed','numeric_excerpt_and_unit_consistency':'passed',
            'physical_page_bounds':'passed','observations':len(data['observations']),
            'sources':len(data['sources']),'datasets':len(data['datasets']),
            'source_availability':'not_checked','evidence_correctness':'not_established_by_schema_checks'}

def money(o):
    require(o['unit'] in MONETARY, 'Monetary input required')
    return number(o['value'])*MONETARY[o['unit']], o['unit'].split('_')[0]

def reconcile(recipe,data):
    """Do not guess through missing or incompatible market dimensions.

    Explicit transformation records are supported for currency conversion and
    proportional allocation. They make the output a scenario estimate, never
    an independently reported observation.
    """
    reasons=[]; ids=[recipe.get('numerator_id'),recipe.get('denominator_id')]
    inputs=[data['observations'].get(i) for i in ids]
    for label,i,o in zip(('numerator','denominator'),ids,inputs):
        if o is None: reasons.append(f'Missing {label}: {i or "not acquired"}')
        elif o['evidence']['status']!='source_checked': reasons.append(f'{label} not source checked')
        else:
            # Reference market data is recorded for context, not as a computation input. An analyst
            # category estimate is not a verified denominator: its population, geography and product
            # boundary are the analyst's, not ours, and using one silently adopts all three.
            src=data.get('sources',{}).get(o.get('source_id')) or {}
            status=(data.get('datasets',{}).get(src.get('dataset_id')) or {}).get('status')
            if status=='reference_only' and recipe.get('reference_input_approved') is not True:
                reasons.append(f'{label} is reference market data, not an approved denominator: '
                               f'set reference_input_approved on the recipe and state why its population, '
                               f'geography and product boundary match this numerator')
    implied=recipe['kind']=='implied_market_size'
    result={'reconciliation_id':recipe['reconciliation_id'],'question':recipe['question'],
            'input_observation_ids':[i for i in ids if i], 'assumptions':recipe.get('adjustments',[]),
            'status':'blocked','value':None,'unit':'percent','reasons':reasons,
            'formula':'100 * adjusted revenue / reported share percent' if implied else '100 * adjusted numerator / adjusted denominator', 'result_kind':'derived'}
    if any(o is None for o in inputs):
        result['reasons'] += recipe.get('known_gaps',[])
        return result
    import copy
    from .qualifiers import interval, scale_interval, ratio_interval, result_fields
    n,d=copy.deepcopy(inputs); amounts=[]; currencies=[]; bounds=[]
    result['input_qualifiers']=[{'observation_id':o['observation_id'],'relation':o['relation'],'precision':o['precision']} for o in inputs]
    for j,o in enumerate((n,d)):
        if implied and j==1:
            if o['unit']!='percent' or o['metric_id']!='reported_market_share':reasons.append('Implied size requires an analyst share in percent');return result
            amounts.append(number(o['value']));currencies.append(currencies[0]);continue
        if o['unit'] not in MONETARY:
            reasons.append('This reconciliation requires monetary revenue inputs');return result
        a,c=money(o);amounts.append(a);currencies.append(c)
    try:
        bounds=[interval(o,number(1) if implied and j==1 else MONETARY[o['unit']]) for j,o in enumerate((n,d))]
    except ValidationError as exc:
        reasons.append(str(exc));return result
    for adjustment in recipe.get('adjustments',[]):
        require(adjustment.get('assumption_id') and adjustment.get('rationale') and adjustment.get('evidence_status') in {'assumed','source_checked'},'Adjustment needs explicit provenance/status')
        side=adjustment['side']; require(side in {'numerator','denominator'},'Invalid adjustment side')
        j=0 if side=='numerator' else 1; target=(n,d)[j]
        factor=number(adjustment['factor']); require(factor>0,'Adjustment factor must be positive')
        if adjustment['operation']=='allocate':
            require(factor<=1,'Allocation factor exceeds one')
            changes=adjustment['dimension_changes']
            require(set(changes)<=set(DIMENSIONS)|{'category_id','reporting_scope_id'},'Unsupported allocation dimension')
            for k,v in changes.items():
                if k in DIMENSIONS:target['dimensions'][k]=v
                else:target[k]=v
        elif adjustment['operation']=='currency_convert':
            require(target['unit'] in MONETARY,'Currency conversion cannot target a percentage or count')
            require(adjustment['to_currency'] in {'CNY','USD'},'Unsupported currency')
            currencies[j]=adjustment['to_currency']
        else:raise ValidationError('Unsupported adjustment; implement and test before use')
        amounts[j]*=factor
        bounds[j]=scale_interval(bounds[j],factor)
    if n['period']!=d['period']: reasons.append('Reporting intervals/time bases differ')
    if not implied and currencies[0]!=currencies[1]: reasons.append('Currency differs; explicit FX adjustment required')
    if n['metric_id']!='revenue': reasons.append('Numerator is not revenue')
    if recipe['kind']=='company_revenue_mix':
        if d['metric_id']!='revenue' or n['entity_id']!=d['entity_id']: reasons.append('Company revenue mix requires one company and revenue metrics')
        bridge=recipe.get('scope_bridge',{})
        if bridge.get('numerator_scope')!=n['reporting_scope_id'] or bridge.get('denominator_scope')!=d['reporting_scope_id'] or not bridge.get('rationale'):
            reasons.append('Explicit portfolio scope bridge missing')
        dimensions=('geography','geography_basis','revenue_basis','price_basis','equipment_condition','tax_basis')
    elif recipe['kind'] in {'market_share','implied_market_size'}:
        if not implied and (d['metric_id']!='market_size' or d['entity_id']!='market'): reasons.append('Denominator is not a market aggregate')
        if implied and d['entity_id']!=n['entity_id']:reasons.append('Revenue and reported share refer to different vendors')
        if n['category_id']!=d['category_id']: reasons.append('Equipment category differs')
        if n['reporting_scope_id']!=d['reporting_scope_id']:
            bridge=recipe.get('scope_bridge',{})
            if bridge.get('numerator_scope')!=n['reporting_scope_id'] or bridge.get('denominator_scope')!=d['reporting_scope_id'] or not bridge.get('rationale'):
                reasons.append('Reporting scopes differ; explicit scope bridge required')
        if n['platform_id'] or d['platform_id']:reasons.append('Platform-to-market scope requires a dedicated mapping')
        if not d.get('market_definition_id'):reasons.append('Denominator market definition missing')
        dimensions=DIMENSIONS
    else:raise ValidationError('Unknown reconciliation kind')
    dimensions=set(dimensions) | ((set(n['dimensions']) | set(d['dimensions']))-set(DIMENSIONS))
    for dim in sorted(dimensions):
        x,y=n['dimensions'].get(dim,'unknown'),d['dimensions'].get(dim,'unknown')
        if x!=y:reasons.append(f'{dim} differs: {x} vs {y}')
        elif not isinstance(x,str) or x.lower() in {'unknown','not_disclosed',''}:reasons.append(f'{dim} unknown')
    try:
        ratio=ratio_interval(*bounds)
    except ValidationError as exc:
        reasons.append(str(exc));return result
    if not reasons:
        if not implied and (ratio['lower']>100 or (ratio['lower']==100 and not ratio['lower_closed'])):
            reasons.append('Ratio exceeds 100%; unresolved scope/estimate inconsistency')
        else:
            if not implied and (ratio['upper'] is None or ratio['upper']>100):
                ratio.update(upper=number(100),upper_closed=True)
                result['constraints_applied']=['Intersected the propagated interval with the defined 0–100% share/revenue-mix domain.']
            result.update(status='computed',unit=currencies[0] if implied else 'percent',
                          result_kind='scenario_estimate' if recipe.get('adjustments') else 'implied_estimate' if implied else 'derived_ratio',
                          **result_fields(ratio))
            if any(o['relation']=='approaching' for o in inputs):
                result['uncertainty_note']+=' Uses the source’s approaching threshold as an approximate calculation anchor; no distance or direction from that threshold is inferred.'
    return result

def verify_assets(root=ROOT):
    data=load(root); paths=read_json(root/'local/source_paths.json');results=[]
    for sid,s in data['sources'].items():
        p=Path(paths.get(sid,'')); state='missing'
        from .library import _allowed
        if not _allowed(p):state='protected_path'
        elif p.is_file():state='verified' if digest(p)==s['sha256'] else 'hash_mismatch'
        results.append({'source_id':sid,'status':state})
    return results

def input_hashes(root):
    return {p.relative_to(root).as_posix():digest(p) for folder in ('data','atlas') for p in sorted((root/folder).rglob('*')) if p.suffix in {'.json','.py'} and '__pycache__' not in p.parts}

def display(o):
    prefix={'eq':'','gt':'>','ge':'≥','lt':'<','le':'≤','approx':'≈','approaching':'approaching ','range':''}[o['relation']]
    value=f'{number(o["value"]):,}'
    if o['relation']=='range':value+='–'+f'{number(o["upper_value"]):,}'
    return prefix+value+' '+o['unit']

def source_link(o,data):
    s=data['sources'][o['source_id']];url=s.get('url','')
    if url:
        if '.pdf' in url.lower():url+=f"#page={o['evidence']['page']}"
        return f"[{s['title']}, p.{o['evidence']['page']}]({url})"
    return f"{s['title']}, PDF p.{o['evidence']['page']} (local source: `{s['source_id']}`)"

def table(headers,rows):
    def cell(v):return str(v).replace('|','\\|').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(cell(x) for x in r)+' |' for r in rows])

def display_scope(o):
    parts=[o['platform_id'] or o['reporting_scope_id']]
    dims=o['dimensions']
    if dims.get('counterparty_bucket'):parts.append(dims['counterparty_bucket'])
    if dims.get('reported_counterparty_name'):parts.append(dims['reported_counterparty_name'])
    if dims.get('workforce_group'):parts.extend(dims[k] for k in ('workforce_group','workforce_breakdown','workforce_cohort') if dims.get(k))
    for key in ('cost_component','sales_channel'):
        if dims.get(key):parts.append(dims[key])
    if dims.get('geography_basis')=='issuer_reported_region_definition_not_disclosed':parts.append(dims['geography'])
    if dims.get('process_node'):parts.extend([dims['process_node'],dims['process_node_context']])
    for key in ('shareholder_table','shareholder_rank','reported_holder_name','holding_basis','share_class'):
        if key in dims:parts.append(str(dims[key]))
    return ' / '.join(parts)

def observation_export(o, series_id='', named_series_ids=(), ancestors=None):
    """Flatten measurement identity without dropping bounds or time semantics."""
    row={'series_id':series_id,'observation_id':o['observation_id'],'date':o['period']['end'],
         'metric':o['metric_id'],'value':o['value'],'upper_value':o.get('upper_value',''),
         'relation':o['relation'],'precision':o['precision'],'unit':o['unit'],
         'source_id':o['source_id'],'dataset_id':o['dataset_id'],'pdf_page':o['evidence']['page'],
         'original_label':o['evidence']['original_label'],
         'reported_value':o['evidence']['reported_value'],'reported_unit':o['evidence']['reported_unit'],
         'reported_upper_value':o['evidence'].get('reported_upper_value',''),
         'conversion_factor':o['evidence'].get('conversion',{}).get('factor',''),
         'conversion_sign_basis':o['evidence'].get('conversion',{}).get('sign_basis',''),
         'entity_id':o['entity_id'],
         'parent_entity_id':(ancestors or {}).get(o['entity_id'],[''])[0] if (ancestors or {}).get(o['entity_id']) else '',
         'ancestor_entity_ids':';'.join((ancestors or {}).get(o['entity_id'],[])),
         'category_id':o['category_id'],'reporting_scope_id':o['reporting_scope_id'],
         'platform_id':o['platform_id'],'period_start':o['period'].get('start') or '',
         'period_end':o['period']['end'],'period_kind':o['period']['kind'],'period_basis':o['period']['basis'],
         'dimensions_json':json.dumps(o['dimensions'],sort_keys=True,ensure_ascii=False),
         'evidence_status':o['evidence']['status'],'reviewer':o['evidence'].get('reviewer',''),
         'review_date':o['evidence'].get('review_date',''),'claim_kind':o['claim_kind'],
         'revision_of':o['revision_of'],'named_series_ids':';'.join(named_series_ids),
         'selection_status':'selected' if named_series_ids else 'not_selected', 'notes':o['notes']}
    row.update({k:o['dimensions'][k] for k in DIMENSIONS})
    row.update({k:o['dimensions'].get(k,'') for k in ('counterparty_bucket','reported_counterparty_name','workforce_group','workforce_breakdown','workforce_cohort','process_node','process_node_context','cost_component','sales_channel','shareholder_table','shareholder_rank','reported_holder_name','holding_basis','share_class')})
    return row

def build(root=ROOT, *, dependencies=False, views=False):
    data=load(root); report=validate(data,root);results=[reconcile(r,data) for r in data['reconciliations']]
    out=root/'build';out.mkdir(exist_ok=True)
    write_json(out/'validation.json',report);write_json(out/'reconciliation_results.json',results)
    # Canonical JSON already lives in data/. Remove retired generated duplicates.
    for name in ('atlas_observations_v2.json', 'series.csv', 'dependencies.json'):
        (out/name).unlink(missing_ok=True)
    if not views:
        for name in ('Atlas Data View.md', 'Atlas Reconciliation View.md', 'Atlas Coverage View.md', 'coverage.json'):
            (out/name).unlink(missing_ok=True)
    hashes=input_hashes(root)
    try: commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:commit='uncommitted'
    manifest={'schema_version':2,'git_commit':commit,'input_hashes':hashes,
              'input_snapshot_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
              'runtime':'Python standard library; CI Python 3.12','reconciliation_results':results}
    write_json(out/'run_manifest.json',manifest)
    text=['# Equipment Atlas — Evidence View','',
          f"{len(data['observations'])} source observations · {len(data['sources'])} originals · schema version 2.",
          '', 'Canonical structured data is in the private atlas repository. This is a generated reading view; edit prose in your separate Obsidian analysis page.',
          '', 'See [[Atlas Coverage View]] for the platform landscape, application evidence, reviewed source sets and remaining research tasks.',
          '', '## Evidence Series','']
    from .entities import entity_ancestors
    ancestors=entity_ancestors(data['entities'])
    csv_rows=[]
    membership={oid:[] for oid in data['observations']}
    for s in data['series']:
        for oid in s['observation_ids']:membership[oid].append(s['series_id'])
    for s in data['series']:
        text+=['### '+s['title'],'',s['definition'],'',s['limitations'],'']
        rows=[]
        for oid in s['observation_ids']:
            o=data['observations'][oid]
            rows.append([oid,o['period']['end'],display_scope(o),o['metric_id'],display(o),source_link(o,data)])
            csv_rows.append(observation_export(o,s['series_id'],membership[oid],ancestors))
        text+=[table(['ID','Period end / as of','Scope','Metric','Value','Source'],rows),'']
    unselected=[o for oid,o in data['observations'].items() if not membership[oid]]
    text+=['## Observations Outside Named Series','',
           'Not selected is not rejected. These ledger records remain visible with their review status; no comparability or additive relationship is implied.','',
           table(['ID','Period start','Period end / as of','Entity / scope','Metric','Value','Review status','Source'],
                 [[o['observation_id'],o['period'].get('start') or '',o['period']['end'],o['entity_id']+' / '+display_scope(o),o['metric_id'],display(o),o['evidence']['status'],source_link(o,data)] for o in unselected]),'']
    text+=['## Coverage and Outstanding Work','',table(['Scope','Status','Sources reviewed','Next action'],[[c['scope'],c['status'],', '.join(c['reviewed_source_ids']),c['next_action']] for c in data['coverage']]),'',
           '## Evidence Limits','','Company and subsidiary figures may overlap. CSV exports identify current parent/ancestor relationships; these are not historical consolidation dates. Do not sum related entities without a verified consolidation bridge.','','Source checking verifies transcription and interpretation, not independent corroboration of supplier claims. Reviewed coverage is limited to the listed sources. No commercial analyst dataset has been acquired in this pilot.','']
    if views: (out/'Atlas Data View.md').write_text('\n'.join(text),encoding='utf-8')
    model=['# Equipment Atlas — Reconciliation Pilot','',
           'Derived calculations and unresolved model designs. These are not new independent source observations. No external analyst figures have been invented.','']
    for r in results:
        model+=['## '+r['question'],'',f"Status: **{r['status']}**. Result type: {r['result_kind']}.",'',
                'Inputs: '+', '.join(r['input_observation_ids'])+'.', '', 'Formula: `'+r['formula']+'`.','']
        from .qualifiers import display_result
        if r['status']=='computed':model += [f"Result: **{display_result(r)}**.",'']
        if r.get('uncertainty_note'):model += [r['uncertainty_note'],'']
        for constraint in r.get('constraints_applied',[]):model += [constraint,'']
        model+=['- '+x for x in r['reasons']]
        model+=['']
    model+=['The AMEC revenue-mix calculation describes etching revenue as a fraction of AMEC revenue, not Chinese-market share. The China-market recipe remains blocked until geography, market scope and denominator evidence are supplied. Assumed allocations/FX must be separately named and turn results into scenario estimates.','', 'Reproduce with `python -m atlas build`; the run manifest records all data/code hashes and the repository commit.']
    if views: (out/'Atlas Reconciliation View.md').write_text('\n'.join(model),encoding='utf-8')
    all_rows=[observation_export(o,named_series_ids=membership[oid],ancestors=ancestors) for oid,o in data['observations'].items()]
    fields=list(all_rows[0]) if all_rows else []
    for name,rows in [('all_observations.csv',all_rows)]:
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    from .research import build_research
    if views:
        build_research(root, dependencies=dependencies)
    elif dependencies:
        from .research import dependency_state
        write_json(out/'dependencies.json', dependency_state(root))
    return manifest

def snapshot(root,destination):
    """Portable input bundle. Excludes originals, local paths and the whole vault."""
    import shutil
    destination=Path(destination)
    require(not destination.exists(),'Snapshot destination already exists')
    require(not any(destination.resolve().is_relative_to((root/n).resolve()) for n in ('data','atlas','build')),'Snapshot destination cannot be inside inputs or generated build')
    allowed_outputs={'validation.json','reconciliation_results.json','run_manifest.json','Atlas Data View.md',
                     'Atlas Reconciliation View.md','series.csv','all_observations.csv','coverage.json',
                     'dependencies.json','Atlas Coverage View.md','atlas_observations_v2.json'}
    def inventory(folder, suffix=None):
        require(not folder.is_symlink(),'Snapshot refuses symlink directory: '+str(folder))
        paths=[]
        for p in sorted(folder.rglob('*')):
            require(not p.is_symlink(),'Snapshot refuses symlink: '+str(p))
            if '__pycache__' in p.relative_to(folder).parts: continue
            if p.is_dir():continue
            require(p.is_file(),'Snapshot requires regular file: '+str(p))
            require((p.suffix==suffix) if suffix else (p.parent==folder and p.name in allowed_outputs),
                    'Unexpected snapshot file: '+str(p))
            paths.append(p)
        return paths
    inputs=inventory(root/'data','.json')+inventory(root/'atlas','.py')
    if (root/'build').exists():inventory(root/'build')
    build(root)
    outputs=inventory(root/'build')
    hashes=read_json(root/'build/run_manifest.json')['input_hashes']
    require(set(hashes)=={p.relative_to(root).as_posix() for p in inputs},'Snapshot inputs do not match build manifest')
    destination.mkdir(parents=True)
    for p in inputs+outputs:
        relative=p.relative_to(root)
        if relative.parts[0]=='build':relative=Path('outputs')/Path(*relative.parts[1:])
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    return destination
