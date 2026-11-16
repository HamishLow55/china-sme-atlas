"""Bounded, local-only document retrieval. Search hits are leads, not evidence."""
import hashlib
from contextlib import closing
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess

EXCLUDED = {'Semis notes', '_Unsourced (do not cite)'}
EXTENSIONS = {'.pdf', '.md', '.csv', '.txt'}
CACHE_VERSION = 1
DEFAULT_ALIASES = {'amec': ['中微', '中微公司', 'china micro', 'china+micro'],
                   'naura': ['北方华创']}


def _allowed(path):
    return not (EXCLUDED.intersection(path.parts) or EXCLUDED.intersection(path.resolve().parts))


def _files(paths):
    """Prune forbidden directories before traversal; never traverse directory links."""
    found, excluded = set(), set()
    for value in paths:
        root = Path(value).absolute()
        if not _allowed(root):
            excluded.add(str(root))
            continue
        if root.is_file():
            if root.suffix.lower() in EXTENSIONS:
                found.add(root)
            continue
        if not root.is_dir():
            continue
        real_root = root.resolve()
        for directory, dirs, files in os.walk(root, followlinks=False):
            base = Path(directory)
            kept = []
            for name in dirs:
                p = base / name
                if _allowed(p) and not p.is_symlink():
                    kept.append(name)
                else:
                    excluded.add(str(p))
            dirs[:] = kept
            for name in files:
                p = base / name
                if not _allowed(p) or not p.resolve().is_relative_to(real_root):
                    excluded.add(str(p))
                elif p.suffix.lower() in EXTENSIONS and p.is_file():
                    found.add(p)
    return sorted(found), sorted(excluded)


def _extract(path):
    try:
        if path.suffix.lower() == '.pdf':
            result = subprocess.run(['pdftotext', '-layout', str(path), '-'],
                                    capture_output=True, text=True, timeout=60, check=True)
            pages = result.stdout.split('\f')
            if pages and not pages[-1].strip():
                pages.pop()
        else:
            pages = [path.read_text(encoding='utf-8-sig', errors='replace')]
        return {'status': 'extracted' if any(p.strip() for p in pages) else 'empty',
                'pages': pages, 'error': ''}
    except (OSError, subprocess.SubprocessError) as exc:
        return {'status': 'failed', 'pages': [], 'error': str(exc)}


def index_library(paths, local_dir, sources):
    """Replace the inventory for explicit roots, reusing hash-keyed extraction caches.

    File bytes are hashed every run: unchanged timestamps cannot hide an edit.
    Failed extractions are retried. Originals are never modified.
    """
    local = Path(local_dir)
    if not _allowed(local):
        raise ValueError('Protected library output path')
    cache_dir = local / 'library_cache'
    if not _allowed(cache_dir) or not _allowed(local / 'library.sqlite'):
        raise ValueError('Protected library cache or database path')
    cache_dir.mkdir(parents=True, exist_ok=True)
    records = list(sources.values()) if isinstance(sources, dict) else list(sources)
    source_ids = {}
    for record in records:
        source_ids.setdefault(record['sha256'], []).append(record['source_id'])
    files, excluded = _files(paths)
    documents, locations = {}, []
    extracted = cached = 0
    for path in files:
        # Recheck immediately before opening, including resolved symlink target.
        if not _allowed(path):
            excluded.append(str(path))
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha not in documents:
            cache = cache_dir / (sha + '.json')
            if not _allowed(cache) or not _allowed(cache.with_suffix('.tmp')):
                raise ValueError('Protected extraction cache path')
            value = None
            if cache.exists():
                try:
                    candidate = json.loads(cache.read_text(encoding='utf-8'))
                    if (candidate.get('version') == CACHE_VERSION and
                            candidate.get('kind') == path.suffix.lower() and
                            candidate.get('status') in {'extracted', 'empty'}):
                        value = candidate
                except (ValueError, OSError):
                    pass
            if value is None:
                value = dict(_extract(path), version=CACHE_VERSION, kind=path.suffix.lower())
                temp = cache.with_suffix('.tmp')
                temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
                temp.replace(cache)
                extracted += 1
            else:
                cached += 1
            documents[sha] = value
        value = documents[sha]
        ids = sorted(source_ids.get(sha, []))
        locations.append({'path': str(path), 'sha256': sha, 'source_id': ids[0] if ids else '',
                          'source_ids': ids, 'extraction_status': value['status'],
                          'page_count': len(value['pages']), 'error': value['error']})
    with closing(sqlite3.connect(local / 'library.sqlite')) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS documents (sha256 TEXT PRIMARY KEY, source_ids TEXT, status TEXT, error TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS locations (path TEXT PRIMARY KEY, sha256 TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS pages (sha256 TEXT, page INTEGER, text TEXT, PRIMARY KEY(sha256,page))')
        for table in ('documents', 'locations', 'pages'):
            db.execute('DELETE FROM ' + table)
        for sha, value in documents.items():
            db.execute('INSERT INTO documents VALUES (?,?,?,?)',
                       (sha, json.dumps(sorted(source_ids.get(sha, []))), value['status'], value['error']))
            db.executemany('INSERT INTO pages VALUES (?,?,?)',
                           [(sha, i, text) for i, text in enumerate(value['pages'], 1)])
        db.executemany('INSERT INTO locations VALUES (?,?)', [(r['path'], r['sha256']) for r in locations])
    return {'catalogued_locations': len(locations), 'unique_content_hashes': len(documents),
            'pages': sum(len(d['pages']) for d in documents.values()), 'extracted': extracted,
            'cached': cached, 'failures': sum(d['status'] == 'failed' for d in documents.values()),
            'records': locations, 'excluded_paths': sorted(set(excluded))}


def _term_positions(text, term):
    """Digits match whole numeric runs; Chinese and words retain substring search."""
    if term.isdecimal():
        return [m.start() for m in re.finditer(r'(?<![\d,.])' + re.escape(term) + r'(?![\d,])', text)]
    positions, start = [], 0
    while len(positions) < 50:
        pos = text.find(term, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + max(1, len(term))
    return positions


def search_library(query, local_dir, aliases=None, limit=10, source_ids=None):
    """Return deduplicated page hits; token AND, alias OR, literal substring matching."""
    words = query.casefold().split()
    if not words or limit < 1:
        raise ValueError('Provide a nonempty query and positive limit')
    path = Path(local_dir) / 'library.sqlite'
    if not _allowed(path):
        raise ValueError('Protected library path')
    if not path.exists():
        raise FileNotFoundError('Run library indexing first')
    mapping = dict(DEFAULT_ALIASES)
    mapping.update(aliases or {})
    groups, variants_by_phrase = [], {}
    fold=lambda s: ' '.join(s.casefold().split())
    for name,values in mapping.items():
        values=[values] if isinstance(values,str) else values
        variants={fold(name),*(fold(str(v)) for v in values)}
        for phrase in variants:variants_by_phrase.setdefault(phrase,set()).update(variants)
    # Resolve complete multiword aliases before splitting the remaining query.
    # Otherwise 'ACM Research' cannot retrieve a Chinese-only 盛美上海 passage.
    i=0
    while i<len(words):
        for width in range(len(words)-i,0,-1):
            phrase=' '.join(words[i:i+width])
            if phrase in variants_by_phrase:
                groups.append(sorted(variants_by_phrase[phrase]));i+=width;break
        else:
            groups.append([words[i]]);i+=1
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        # Python casefold keeps Chinese substring and Unicode matching predictable.
        db.create_function('fold', 1, fold)
        clauses, params = [], []
        for group in groups:
            clauses.append('(' + ' OR '.join('instr(fold(p.text || char(10) || l.names), ?) > 0' for _ in group) + ')')
            params.extend(group)
        sql = '''SELECT p.*, d.source_ids, d.status, l.names FROM pages p
                 JOIN documents d USING(sha256)
                 JOIN (SELECT sha256, group_concat(path, char(10)) names FROM locations GROUP BY sha256) l USING(sha256)
                 WHERE ''' + ' AND '.join(clauses)
        rows = db.execute(sql, params).fetchall()
        ranked = []
        for row in rows:
            ids = json.loads(row['source_ids'])
            if source_ids is not None and not set(ids).intersection(source_ids):
                continue
            body = fold(row['text'])
            context = body + '\n' + fold(row['names'])
            if not all(any(_term_positions(context, t) for t in g) for g in groups):
                continue
            positions = [[pos for t in group for pos in _term_positions(body, t)] for group in groups]
            matched = sum(bool(p) for p in positions)
            # Repeated corporate headers should not outweigh direct matching passages.
            density = sum(min(len(p), 5) for p in positions) / max(len(body), 200)
            phrase = int(' '.join(words) in body)
            literal_matches = sum(bool(_term_positions(body,w)) for w in words)
            score = (bool(ids), matched == len(groups), matched, literal_matches, phrase, density)
            ranked.append((score, row, positions))
        ranked.sort(key=lambda item: (tuple(-float(x) for x in item[0]), item[1]['sha256'], item[1]['page']))
        results = []
        for score, row, positions_by_group in ranked:
            paths = [r[0] for r in db.execute('SELECT path FROM locations WHERE sha256=? ORDER BY path', (row['sha256'],))]
            # A source moved under a protected path after indexing is never reopened.
            paths = [p for p in paths if _allowed(Path(p))]
            if not paths:
                continue
            text = ' '.join(row['text'].split())
            # Last query token usually carries the requested metric/platform detail.
            positions = next((p for p in reversed(positions_by_group) if p), [])
            start = max(0, min(positions, default=0) - 100)
            ids = json.loads(row['source_ids'])
            results.append({'path': paths[0], 'paths': paths, 'sha256': row['sha256'],
                            'source_id': ids[0] if ids else '', 'source_ids': ids, 'page': row['page'],
                            'snippet': text[start:start + 550].strip(), 'extraction_status': row['status'],
                            'matched_text_groups': score[2], 'registered_source': bool(ids)})
            if len(results) >= limit:
                break
        return results
