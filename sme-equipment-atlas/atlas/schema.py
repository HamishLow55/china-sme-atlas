"""Evaluate the JSON Schema vocabulary used by the declared observation contract.

Standard-library implementation; deliberately limited to the documented vocabulary.
Unknown assertion keywords fail closed instead of silently weakening the contract.
"""
import re
from datetime import date

ANNOTATIONS={'$schema','$id','title','description','$comment','examples','default'}
ASSERTIONS={'type','properties','required','additionalProperties','enum','const','pattern','minLength','maxLength','minItems','maxItems','minimum','maximum','format','anyOf','items','$defs','$ref','x-atlas-registry-constraints','x-atlas-units','x-atlas-registries','x-atlas-metric-dimensions','x-atlas-node-claims','x-atlas-percent-semantics','x-atlas-source-decrease','x-atlas-source-loss','x-atlas-platform-maturity-date'}

def unbounded_percent_metric(metric,schema,require):
    policy=schema['x-atlas-percent-semantics']
    require(set(policy)=={'metric_field','unbounded_values','unit','default_maximum'},'Invalid percent semantics policy')
    field=policy['metric_field']
    if field not in metric:return False
    require(metric[field] in policy['unbounded_values'],'Unknown metric percent semantics')
    require(metric['units']==[policy['unit']],'Unbounded percent semantics require only percent units')
    return True

def source_decrease_metric(metric,schema,require):
    policy=schema['x-atlas-source-decrease']
    require(set(policy)=={'metric_flag'},'Invalid source decrease policy')
    field=policy['metric_flag']
    if field not in metric:return False
    require(metric[field] is True and metric.get('allow_negative') is True,'Source decrease interpretation requires an explicit signed-change metric')
    return True

def source_loss_metric(metric,schema,require):
    policy=schema['x-atlas-source-loss']
    require(set(policy)=={'metric_flag'},'Invalid source loss policy')
    field=policy['metric_flag']
    if field not in metric:return False
    require(metric[field] is True and metric.get('allow_negative') is True,'Source loss interpretation requires an explicitly signed metric')
    return True

def validate_shape(value, schema, require, path='observation', document=None):
    document=schema if document is None else document
    require(not set(schema)-ANNOTATIONS-ASSERTIONS,f'{path}: unsupported schema keywords {set(schema)-ANNOTATIONS-ASSERTIONS}')
    if '$ref' in schema:
        ref=schema['$ref'];require(ref.startswith('#/'),f'{path}: only local schema references supported')
        target=document
        for part in ref[2:].split('/'):target=target[part.replace('~1','/').replace('~0','~')]
        validate_shape(value,target,require,path,document)
    if 'anyOf' in schema:
        errors=[]
        for choice in schema['anyOf']:
            try:validate_shape(value,choice,require,path,document)
            except ValueError as exc:errors.append(str(exc))
            else:break
        else:require(False,f'{path}: no allowed schema alternative matches')
    if 'type' in schema:
        kinds={'object':lambda v:isinstance(v,dict),'array':lambda v:isinstance(v,list),'string':lambda v:isinstance(v,str),'integer':lambda v:type(v) is int,'number':lambda v:type(v) in {int,float},'boolean':lambda v:type(v) is bool,'null':lambda v:v is None}
        require(schema['type'] in kinds,f'{path}: unsupported schema type')
        require(kinds[schema['type']](value),f'{path}: expected {schema["type"]}')
    if 'enum' in schema:require(value in schema['enum'],f'{path}: value outside declared enum')
    if 'const' in schema:require(value==schema['const'],f'{path}: wrong constant')
    if isinstance(value,dict):
        props=schema.get('properties',{})
        require(set(schema.get('required',[]))<=set(value),f'{path}: missing declared fields {set(schema.get("required",[]))-set(value)}')
        if schema.get('additionalProperties') is False:require(set(value)<=set(props),f'{path}: unknown fields {set(value)-set(props)}')
        for key,item in value.items():
            if key in props:validate_shape(item,props[key],require,f'{path}.{key}',document)
    if isinstance(value,list):
        if 'minItems' in schema:require(len(value)>=schema['minItems'],f'{path}: too few array items')
        if 'maxItems' in schema:require(len(value)<=schema['maxItems'],f'{path}: too many array items')
        if 'items' in schema:
            for i,item in enumerate(value):validate_shape(item,schema['items'],require,f'{path}[{i}]',document)
    if isinstance(value,str):
        if 'minLength' in schema:require(len(value)>=schema['minLength'],f'{path}: string too short')
        if 'maxLength' in schema:require(len(value)<=schema['maxLength'],f'{path}: string too long')
        if 'pattern' in schema:require(re.search(schema['pattern'],value) is not None,f'{path}: invalid string pattern')
        if schema.get('format')=='date':
            require(re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) is not None,f'{path}: expected ISO date')
            date.fromisoformat(value)
        elif 'format' in schema:require(False,f'{path}: unsupported format')
    if type(value) in {int,float}:
        if 'minimum' in schema:require(value>=schema['minimum'],f'{path}: below minimum')
        if 'maximum' in schema:require(value<=schema['maximum'],f'{path}: above maximum')

def registry_constraints(observation,data,schema,require):
    for rule in schema.get('x-atlas-registry-constraints',[]):
        require(set(rule)=={'field','registry','lookup_field','allowed_values_field'},'Invalid schema registry constraint')
        value=observation
        for part in rule['field'].split('.'):value=value[part]
        rid=observation[rule['lookup_field']]
        record=data[rule['registry']].get(rid)
        require(record is not None,f'{observation["observation_id"]}: unknown {rule["lookup_field"]}')
        require(value in record[rule['allowed_values_field']],f'{observation["observation_id"]}: {rule["field"]} incompatible with {rid}')

    constraint=schema.get('x-atlas-metric-dimensions')
    if constraint:
        require(set(constraint)=={'registry','lookup_field','schema_field','value_field'},'Invalid metric dimension contract')
        metric=data[constraint['registry']].get(observation[constraint['lookup_field']])
        if metric and metric.get(constraint['schema_field']):
            validate_shape(observation[constraint['value_field']],metric[constraint['schema_field']],require,observation['observation_id']+'.metric_dimensions')


def validate_node_fields(container,evidence,schema,require,path,measurement_scope=None):
    policy=schema['x-atlas-node-claims']
    claim_schema=schema
    for part in policy['fields_schema'][2:].split('/'):
        claim_schema=claim_schema[part]
    fields={key:container[key] for key in claim_schema['properties'] if key in container}
    scope_binding=None if measurement_scope is None else measurement_scope.get(policy['measurement_scope_field'])
    if not fields:
        require(not scope_binding,f'{path}: node-scoped reporting definition requires node dimensions')
        return
    if measurement_scope is not None:
        require(scope_binding is not None,f'{path}: numeric node needs an explicitly node-scoped reporting definition')
        validate_shape(scope_binding,claim_schema,require,path+'.scope_binding',document=schema)
        require(fields==scope_binding,f'{path}: node dimensions differ from reporting-scope binding')
    validate_shape(fields,claim_schema,require,path,document=schema)
    node=fields['process_node'];context=fields['process_node_context']
    require(re.search(r'(?:\d[\d.\s–-]*\s*(?:nm|纳米|奈米|Å|埃)|\b[NnAa]\d+[A-Za-z0-9]*\b|\b\d+A\b)',node) is not None,f'{path}: explicit numerical or named process node required')
    compact=lambda text:re.sub(r'\s+','',text)
    excerpt=compact(evidence.get('excerpt',''))
    require(compact(node) in excerpt,f'{path}: node expression absent from source excerpt')
    require(context=='not_stated' or compact(context) in excerpt,f'{path}: node context absent from source excerpt')
