"""Partition-aware registry IO. File ownership does not imply financial scope."""
import re
import os
import tempfile
import json
from pathlib import Path
from .core import ROOT, read_json, require, digest


def contract(name,root=ROOT):
    definitions=read_json(root/'data/schema.json')['x-atlas-registries']
    require(name in definitions,f'Unknown registry: {name}')
    return definitions[name]


def record_id(row,definition):
    require(isinstance(row,dict),'Registry row must be an object')
    present=[row[k] for k in definition['id_fields'] if row.get(k)]
    require(len(present)==1 and isinstance(present[0],str),'Registry row needs one declared nonempty identity')
    return present[0]


def paths(name,root=ROOT):
    definition=contract(name,root);base=root/'data';single=base/f'{name}.json';directory=base/name
    mode=definition['storage']
    require(mode in {'single','entity_partitions','chunks'},'Unknown registry storage mode')
    if mode=='single':
        require(not directory.exists(),f'{name}: unexpected partition directory beside single registry')
        result=[single]
    else:
        require(not single.exists(),f'{name}: legacy monolith conflicts with partitioned registry')
        require(directory.is_dir() and not directory.is_symlink(),f'{name}: registry directory missing or symlinked')
        require(all(p.is_file() and p.suffix=='.json' for p in directory.iterdir()),f'{name}: unexpected nested or non-JSON registry entry')
        result=sorted(directory.glob('*.json'))
    for p in result:
        require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(base.resolve()),f'{name}: unsafe or missing registry file')
        if mode=='entity_partitions':require(re.fullmatch(r'[A-Za-z0-9_-]+',p.stem),f'{name}: unsafe partition owner')
    return result


def records_with_paths(name,root=ROOT):
    definition=contract(name,root);seen=set();result=[]
    for p in paths(name,root):
        rows=read_json(p);require(isinstance(rows,list),f'{p.name}: expected registry array')
        for row in rows:
            rid=record_id(row,definition);require(rid not in seen,f'{name}: duplicate registry ID {rid}');seen.add(rid)
            field=definition.get('entity_field')
            if definition['storage']=='entity_partitions' and field:
                require(row.get(field)==p.stem,f'{name}: record entity differs from partition owner')
            result.append((row,p))
    return result


def read_records(name,root=ROOT):
    return [row for row,_ in records_with_paths(name,root)]


def record_path(name,rid,root=ROOT):
    matches=[p for row,p in records_with_paths(name,root) if record_id(row,contract(name,root))==rid]
    require(len(matches)==1,f'{name}: missing record {rid}')
    return matches[0]


def validate_partition_owners(root=ROOT):
    expected=expected_owners(root)
    for name,owners in expected.items():
        for row,p in records_with_paths(name,root):
            require(p.stem==owners[record_id(row,contract(name,root))],f'{name}: record differs from derived partition owner')
        entities={r['entity_id'] for r in read_records('entities',root)}
        for p in paths(name,root):require(p.stem=='_shared' or p.stem in entities,f'{name}: unknown partition owner {p.stem}')


def write_partition(name,owner,rows,root=ROOT,expected_sha256=None):
    """Replace one reviewed partition. Never approve evidence or write other owners.

    Caller stages and validates full proposals first. expected_sha256 detects a stale
    existing partition; separate worktrees still govern concurrent edits to one firm.
    """
    definition=contract(name,root)
    require(definition['storage']=='entity_partitions','Writer requires an entity-partitioned registry')
    require(isinstance(owner,str) and re.fullmatch(r'[A-Za-z0-9_-]+',owner),'Unsafe partition owner')
    require(isinstance(rows,list),'Expected partition array')
    target=root/'data'/name/f'{owner}.json'
    entities={r['entity_id'] for r in read_records('entities',root)}
    require(owner=='_shared' or owner in entities or (name=='entities' and len(rows)==1 and rows[0].get('entity_id')==owner),'Unknown partition owner')
    existing=records_with_paths(name,root)
    ids=[record_id(row,definition) for row in rows]
    require(len(ids)==len(set(ids)),'Duplicate IDs in proposed partition')
    elsewhere={record_id(row,definition) for row,p in existing if p!=target}
    require(not elsewhere.intersection(ids),'Proposed IDs already exist in another partition')
    old_ids={record_id(row,definition) for row,p in existing if p==target}
    require(old_ids <= set(ids),'Partition writer cannot remove existing records')
    proposal=[row for row,p in existing if p!=target]+rows
    expected=expected_owners(root,{name:proposal})[name]
    require(all(expected[rid]==owner for rid in ids),'Proposed record differs from derived partition owner')
    field=definition.get('entity_field')
    if field:require(all(row.get(field)==owner for row in rows),'Proposed entity differs from partition owner')
    if target.exists():
        require(expected_sha256 is not None and digest(target)==expected_sha256,'Partition changed or expected hash missing')
    else:require(expected_sha256 is None,'Expected existing partition is missing')
    # Readers reject symlinked registries, including the target if already present.
    staging=root/'local'/'registry_staging'
    staging.mkdir(parents=True,exist_ok=True)
    require(not staging.is_symlink() and staging.resolve().is_relative_to(root.resolve()),'Unsafe registry staging directory')
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=staging,delete=False) as stream:
            tmp=Path(stream.name)
            stream.write(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        os.replace(tmp,target)
    finally:
        if tmp is not None and tmp.exists():tmp.unlink()
    return target


def expected_owners(root=ROOT,overrides=None):
    """Derive filing ownership separately from the entity measured by evidence."""
    definitions=read_json(root/'data/schema.json')['x-atlas-registries']
    tables={name:read_records(name,root) for name in definitions}
    tables.update(overrides or {})
    entities={r['entity_id'] for r in tables['entities']}
    datasets={r['dataset_id']:(r['publisher'] if r.get('publisher') in entities else '_shared') for r in tables['datasets']}
    sources={r['source_id']:datasets.get(r.get('dataset_id'),'_shared') for r in tables['sources']}
    observations={r['observation_id']:r['entity_id'] for r in tables['observations']}
    categories={r['category_id'] for r in tables['categories']}
    users={}
    for rows in tables.values():
        for row in rows:
            if row.get('reporting_scope_id') and row.get('entity_id'):
                users.setdefault(row['reporting_scope_id'],set()).add(row['entity_id'])
    def unique(values):
        values=set(values)
        return next(iter(values)) if len(values)==1 and values <= entities else '_shared'
    result={}
    for name,definition in definitions.items():
        if definition['storage']!='entity_partitions':continue
        ownership=definition['ownership'];owners={}
        for row in tables[name]:
            rid=record_id(row,definition)
            if ownership=='entity_field':owner=row[definition['entity_field']]
            elif ownership=='publisher':owner=datasets[rid]
            elif ownership=='dataset_publisher':owner=sources[rid]
            elif ownership=='scope_users':owner='_shared' if rid=='company' or rid in categories else unique(users.get(rid,[]))
            elif ownership=='observation_entities':owner=unique(observations.get(oid) for oid in row['observation_ids'])
            elif ownership=='reviewed_source_publishers':owner=unique(sources.get(sid) for sid in row['reviewed_source_ids'])
            elif ownership=='claim_source_publishers':
                ids=list(row.get('source_ids',[]))+([row['source_id']] if row.get('source_id') else [])
                owner=unique(sources.get(sid) for sid in ids)
            else:raise ValueError('Unknown registry ownership rule: '+ownership)
            owners[rid]=owner
        result[name]=owners
    return result
