"""Command line: check reference tables, list and run projects."""
import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from .data import ROOT, Atlas, git_state
from . import manifest, reference

PROJECTS = ROOT/'projects'

def project_module(name):
    path=PROJECTS/name/'run.py'
    if not path.is_file():raise SystemExit(f'Unknown project {name}; see `sme-analysis list`')
    spec=importlib.util.spec_from_file_location(f'projects.{name}',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def main(argv=None):
    parser=argparse.ArgumentParser(prog='sme-analysis');sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('check',help='validate reference tables against the pinned Atlas');p.add_argument('--atlas',type=Path)
    sub.add_parser('list',help='list projects')
    p=sub.add_parser('run',help='run a project and write results/ with a manifest');p.add_argument('project')
    p.add_argument('--atlas',type=Path,help='Atlas checkout to use instead of the pinned submodule')
    p.add_argument('--preview-atlas',type=Path,help='optional second checkout (e.g. an unmerged research branch) for projects that compare coverage')
    args=parser.parse_args(argv)
    if args.command=='check':
        problems=reference.validate(Atlas(args.atlas))
        print(json.dumps({'problems':problems},indent=2));sys.exit(1 if problems else 0)
    if args.command=='list':
        for d in sorted(PROJECTS.iterdir()):
            if (d/'run.py').is_file():print(d.name)
        return
    if args.command=='run':
        mod=project_module(args.project);atlas=Atlas(args.atlas)
        problems=reference.validate(atlas)
        if problems:raise SystemExit('Reference tables invalid:\n'+'\n'.join(problems))
        preview=Atlas(args.preview_atlas,label='preview checkout') if args.preview_atlas else None
        out=PROJECTS/args.project/'results';out.mkdir(parents=True,exist_ok=True);manifest.START_STATE=git_state(ROOT,ignore=manifest.GENERATED)
        print(json.dumps(mod.run(atlas,out,preview=preview),indent=2,ensure_ascii=False,default=str));return

if __name__=='__main__':main()
