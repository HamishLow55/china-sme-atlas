"""Read-only access to an Atlas checkout: evidence ledger and public statistics layer.

Nothing here writes to the Atlas. Every loader records what it read so projects can
write a provenance manifest (see manifest.py).
"""
import hashlib
import json
import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATLAS = ROOT/'sme-equipment-atlas'

def git_state(path, ignore=()):
    """Commit and dirty flag; `ignore` pathspecs (e.g. generated results) do not count as dirty."""
    run=lambda *a:subprocess.run(['git','-C',str(path),*a],capture_output=True,text=True).stdout.strip()
    return {'commit':run('rev-parse','HEAD'),'dirty':bool(run('status','--porcelain','--','.',*[f':!{p}' for p in ignore]))}

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Atlas:
    """One Atlas checkout. `label` names it in manifests without recording machine paths."""
    def __init__(self, root=None, label=None):
        self.root=Path(root or os.environ.get('SME_ATLAS_PATH') or DEFAULT_ATLAS).resolve()
        if not (self.root/'atlas/core.py').is_file():
            raise FileNotFoundError(f'No Atlas checkout at {self.root}; run `git submodule update --init`')
        self.label=label or ('pinned submodule' if self.root==DEFAULT_ATLAS.resolve() else 'override checkout')
        self.state=git_state(self.root);self.inputs={};self._registries=None

    @property
    def registries(self):
        if self._registries is None:
            env={**os.environ,'PYTHONPATH':str(self.root)}
            out=subprocess.run([sys.executable,str(Path(__file__).with_name('atlas_dump.py')),str(self.root)],
                               capture_output=True,text=True,env=env,cwd=self.root)
            if out.returncode:raise RuntimeError('Atlas failed to load: '+out.stderr[-2000:])
            self._registries=json.loads(out.stdout)
        return self._registries

    def observations(self):
        """Flattened observations with a numeric value converted to the unit's base (e.g. CNY, USD)."""
        reg=self.registries;units=reg['units']
        superseded={o['revision_of'] for o in reg['observations'] if o.get('revision_of')}
        rows=[]
        for o in reg['observations']:
            p=o.get('period',{});dim=o.get('dimensions',{});unit=units.get(o.get('unit'),{})
            try:base=float(Decimal(str(o['value']))*Decimal(unit.get('scale','nan')))
            except (InvalidOperation,KeyError,TypeError):base=float('nan')
            rows.append({'observation_id':o['observation_id'],'entity_id':o['entity_id'],'category_id':o['category_id'],
                'metric_id':o['metric_id'],'reporting_scope_id':o.get('reporting_scope_id',''),'value':o['value'],'relation':o.get('relation',''),
                'unit':o.get('unit',''),'base_unit':unit.get('base_unit',''),'value_base':base,'period_start':p.get('start',''),
                'period_end':p.get('end',''),'period_kind':p.get('kind',''),'period_basis':p.get('basis',''),
                'geography':dim.get('geography',''),'service_scope':dim.get('service_scope',''),'precision':o.get('precision',''),
                'claim_kind':o.get('claim_kind',''),'reporting_basis':o.get('reporting_basis',''),
                'review_status':o.get('evidence',{}).get('status',''),'superseded':o['observation_id'] in superseded})
        return pd.DataFrame(rows)

    def statistics(self, relpath, **kw):
        """Read a statistics/ table as text (codes keep leading zeros); records its hash."""
        p=self.root/'statistics'/relpath
        self.inputs['statistics/'+relpath]=sha256(p)
        return pd.read_csv(p,dtype=str,keep_default_na=False,**kw)

def num(series):
    return pd.to_numeric(series.replace('',pd.NA),errors='coerce')
