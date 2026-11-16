"""Check every entity and platform alias against the local source corpus.

An alias is never cited to a page, so it has no excerpt, no page check and no reviewer decision of
its own: it rides into the registry on the evidence of the rows around it. That makes it the one
registry field a fabrication can enter unopposed, and entity identity is the join key, so a wrong
name is what a later search matches on. This is a local-corpus check rather than a test, for the
same reason verify_assets is: source paths are machine-specific and gitignored.

Platform aliases are checked too, and that was added after the second fabrication rather than the
first. This tool was built when an invented Chinese alias was found on an ENTITY; a later wave then
found an invented model number ("SAB8210CWW") on a PLATFORM, which this tool had never looked at.
A platform alias is the more likely fabrication of the two, because a model number is exactly the
kind of string that looks right, and it is what a reader searching for a tool will match on.
"""
import re
import subprocess
from pathlib import Path

from .core import ROOT, read_json, load


def _text(path):
    """Both pdftotext renderings, concatenated, because each hides strings the other shows.

    `-layout` reconstructs a page by lines, so in a narrow multi-column table it interleaves the
    columns and a cell's text is not contiguous — which made every alias printed inside a table read
    as unsourced. Plain extraction emits cells in logical order and finds those, but loses strings
    that only read correctly across a laid-out line. Searching the concatenation of both is strictly
    better than either, and the cost is one extra pdftotext pass per source.
    """
    try:
        if str(path).lower().endswith('.pdf'):
            out = []
            for args in (['pdftotext', '-layout', str(path), '-'], ['pdftotext', str(path), '-']):
                out.append(subprocess.run(args, capture_output=True, text=True, timeout=180).stdout)
            return '\n'.join(out)
        return Path(path).read_text(encoding='utf-8', errors='ignore')
    except (OSError, subprocess.SubprocessError):
        return ''


def _norm(text):
    return re.sub(r'\s+', '', text).lower()


def _text_coverage(corpus):
    """Sources a text search cannot see into, so an absence from them proves nothing.

    A scanned filing returns no text at all, and a partly scanned one returns none for the pages
    that are images. Either way an alias printed there is invisible here, so the unsourced count
    has to carry this caveat rather than read as a fabrication count.
    """
    return sorted(sid for sid, text in corpus.items() if len(text) < 200)


def verify_aliases(root=ROOT):
    """Report aliases that occur in no held source, with the entity's own sources named first."""
    data = load(root)
    paths = read_json(root / 'local/source_paths.json') if (root / 'local/source_paths.json').exists() else {}
    publisher = {}
    for sid, source in data['sources'].items():
        dataset = data['datasets'].get(source.get('dataset_id')) or {}
        publisher[sid] = dataset.get('publisher')
    corpus = {sid: _norm(_text(path)) for sid, path in paths.items()}
    everything = ''.join(corpus.values())
    results = []
    unreadable = _text_coverage(corpus)
    own_blobs = {}
    for eid in data['entities']:
        own = [sid for sid, pub in publisher.items() if pub == eid and sid in corpus]
        own_blobs[eid] = ''.join(corpus[sid] for sid in own)

    def classify(eid, alias):
        needle = _norm(alias)
        if not needle:
            return None
        if needle in own_blobs.get(eid, ''):
            return 'in_own_source'
        return 'in_another_entity_source' if needle in everything else 'unsourced'

    for eid, entity in sorted(data['entities'].items()):
        for alias in entity.get('aliases', []):
            state = classify(eid, alias)
            if state:
                results.append({'kind': 'entity', 'entity_id': eid, 'alias': alias, 'status': state})
    for pid, platform in sorted(data['platforms'].items()):
        eid = platform['entity_id']
        for alias in platform.get('aliases', []):
            state = classify(eid, alias)
            if state:
                results.append({'kind': 'platform', 'entity_id': eid, 'platform_id': pid,
                                'alias': alias, 'status': state})
    return {'aliases': results, 'sources_without_text_layer': unreadable}
