"""Provenance manifest written beside every project's results."""
import json
from datetime import date
from .data import ROOT, git_state, sha256
from .reference import REF

# Captured by the CLI before a project writes results, so the manifest records the code
# state that produced them rather than the half-written results tree.
START_STATE = None
GENERATED = ('projects/*/results/*',)

def write(out_dir, project, atlases, assumptions=(), notes='', inputs=()):
    refs={f'reference/{p.name}':sha256(p) for p in sorted(REF.glob('*.csv'))}
    m={'project':project,'run_date':date.today().isoformat(),'analysis_repo':START_STATE or git_state(ROOT,ignore=GENERATED),
       'atlas':[{'label':a.label,**a.state,'inputs':dict(sorted(a.inputs.items()))} for a in atlases],
       'reference_tables':refs,'other_inputs':{str(p.relative_to(ROOT)):sha256(p) for p in inputs},'assumptions_used':list(assumptions),'notes':notes,
       'tier':'Tier 3 (working research) unless promoted after review'}
    (out_dir/'manifest.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n')
    return m
