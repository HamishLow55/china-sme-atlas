"""Consolidation relationships and conservative safeguards for financial totals."""
from .core import require, number, MONETARY, validate_observation


def entity_ancestors(entities):
    result={}
    for eid in entities:
        seen={eid};chain=[];node=entities[eid]
        while node.get('parent_entity_id'):
            parent=node['parent_entity_id']
            require(isinstance(parent,str) and parent in entities,f'{eid}: unknown parent entity')
            require(parent not in seen,f'{eid}: entity parent cycle')
            seen.add(parent);chain.append(parent);node=entities[parent]
        result[eid]=chain
    return result


def assert_no_entity_overlap(entity_ids,entities):
    ancestors=entity_ancestors(entities);ids=list(entity_ids)
    require(all(eid in entities for eid in ids),'Aggregation references unknown entity')
    require(len(ids)==len(set(ids)),'Aggregation repeats an entity; select one reporting vintage and scope')
    selected=set(ids)
    for eid in ids:
        overlap=selected.intersection(ancestors[eid])
        require(not overlap,f'Parent/subsidiary aggregation overlap: {eid} with {sorted(overlap)}')


def aggregate_company_financials(observation_ids,data):
    """Explicit exact subtotal, never a market denominator or consolidation model.

    Current parent links conservatively block even historical pairs; they do not
    establish historical consolidation dates. No intercompany elimination inferred.
    """
    ids=list(observation_ids)
    require(ids and len(ids)==len(set(ids)),'Aggregation needs distinct observation IDs')
    require(all(oid in data['observations'] for oid in ids),'Unknown aggregation observation')
    rows=[data['observations'][oid] for oid in ids]
    assert_no_entity_overlap([o['entity_id'] for o in rows],data['entities'])
    first=rows[0];currency=first['unit'].split('_')[0];total=number('0')
    for o in rows:
        validate_observation(o,data)
        require(o['evidence']['status']=='source_checked','Aggregation input not source checked')
        require(o['precision'] in {'reported','as_reported'},'Exact subtotal requires unqualified reported precision')
        require(o['relation']=='eq','Exact subtotal requires exact inputs; qualifiers must not be discarded')
        require(o['category_id']=='all_businesses' and o['reporting_scope_id']=='company' and not o['platform_id'],'Subtotal requires company-wide financial observations')
        require(o['unit'] in MONETARY and o['unit'].split('_')[0]==currency,'Subtotal requires one monetary currency')
        require(all(o[k]==first[k] for k in ('metric_id','period','dimensions')),'Subtotal inputs have incompatible metrics, periods or reporting dimensions')
        require(all(v not in ('unknown','not_disclosed','') for v in o['dimensions'].values()),'Subtotal reporting dimensions are unknown')
        total+=number(o['value'])*MONETARY[o['unit']]
    return {'input_observation_ids':ids,'value':str(total),'unit':currency,'result_kind':'selected_company_subtotal',
            'limitations':['Selected firms only; not a market denominator or market-size estimate.',
                           'Current parent links checked; historical consolidation exceptions are not inferred.',
                           'No intercompany sales elimination; unrelated firms may still transact with one another.']}
