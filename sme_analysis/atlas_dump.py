"""Run inside an Atlas checkout (PYTHONPATH=<atlas root>) and print its registries as JSON.

Loading each Atlas checkout in its own process keeps the pinned submodule and any
preview checkout (e.g. an unmerged research branch) from sharing imported code.
"""
import json
import sys
from pathlib import Path

def main(root):
    from atlas.core import load
    from atlas.registry import read_records
    root=Path(root).resolve();data=load(root)
    out={'observations':list(data['observations'].values()),'entities':list(data['entities'].values()),
         'datasets':list(data['datasets'].values()),'categories':json.loads((root/'data/categories.json').read_text()),
         'units':json.loads((root/'data/schema.json').read_text())['x-atlas-units']}
    for reg in ('platforms','application_links','sources'):
        try:out[reg]=read_records(reg,root)
        except Exception:out[reg]=[]
    holds=[]
    for f in sorted((root/'data/unresolved_claims').glob('*.json')):
        d=json.loads(f.read_text());holds+=d if isinstance(d,list) else d.get('records',[])
    out['unresolved_claims']=holds
    json.dump(out,sys.stdout,ensure_ascii=False)

if __name__=='__main__':main(sys.argv[1])
