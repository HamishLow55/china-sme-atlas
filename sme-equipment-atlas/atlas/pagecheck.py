"""Read-only local PDF page numeric preflight; not evidence review or promotion."""
import subprocess
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .core import digest
from .evidence import numeric_tokens

def _thousands_text(value):
    """Thousands-separated form of a part, tolerating a part already written with separators."""
    from .evidence import _thousands
    try:
        return _thousands(str(value).replace(',',''))
    except (ValueError,ArithmeticError):
        return str(value)
from .library import _allowed

def native_rows(packet,source_id=None):
    """Adapt numeric native staging to page checks without trusting its excerpts.

    Accept a nonempty row array, or an object with ``rows`` and an optional
    ``source_id`` / ``source.source_id`` default. Every row needs candidate_id,
    physical_page and native_value. Qualitative rows must be explicitly separated
    before calling this adapter; none are silently skipped. Registry metadata and
    local paths inside a packet are never used to resolve or authenticate a PDF.
    """
    from .core import require
    declared=[source_id] if source_id is not None else []
    if isinstance(packet,dict):
        source=packet.get('source',{})
        require(isinstance(source,dict),'Native source metadata must be an object')
        declared += [s for s in [packet.get('source_id'),source.get('source_id')] if s is not None]
        rows=packet.get('rows')
    else:rows=packet
    require(all(isinstance(s,str) and s for s in declared),'Invalid native source identifier')
    require(len(set(declared))<=1,'Conflicting native packet source identifiers')
    default=declared[0] if declared else ''
    require(isinstance(rows,list) and bool(rows),'Expected a nonempty native row array')
    def number(value,unit):
        require(type(value) in (str,int),'Native numeric values must be decimal strings or integers')
        value=str(value).strip().replace('−','-').replace('－','-')
        change=re.fullmatch(r'(?:增加|减少)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*个百分点',value)
        if change:
            require(unit in ('percentage_point','percentage_points'),'Worded point change requires a percentage-point native unit')
            value=change.group(1)  # Printed magnitude only; do not infer its signed measurement.
        if value.endswith(('%','％')):
            require(unit in ('percent','%'),'Native percent suffix requires an explicit percent unit')
            value=value[:-1].strip()
        if value.startswith('(') and value.endswith(')'):
            value='-'+value[1:-1]
        require(re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',value) is not None,
                'Invalid native numeric value; separate qualitative rows and retain numeric bounds explicitly')
        return str(Decimal(value.replace(',','')))
    result=[];seen=set()
    for row in rows:
        require(isinstance(row,dict),'Expected a native row object')
        cid=row.get('candidate_id');sid=row.get('source_id',default)
        require(isinstance(cid,str) and bool(cid) and cid not in seen,'Missing or duplicate native candidate identifier')
        require(isinstance(sid,str) and bool(sid),'Missing native source identifier')
        require(not default or sid==default,'Native row source conflicts with packet source')
        require(type(row.get('physical_page')) is int,'Native physical page must be an integer')
        evidence={'page':row['physical_page'],'reported_value':number(row.get('native_value'),row.get('native_unit'))}
        if row.get('relation')=='range':require('native_upper_value' in row,'Native range needs an explicit upper bound')
        if 'native_upper_value' in row:evidence['reported_upper_value']=number(row['native_upper_value'],row.get('native_unit'))
        result.append({'observation_id':cid,'source_id':sid,'evidence':evidence});seen.add(cid)
    return result

def _pages(pdf):
    try:
        r=subprocess.run(['pdftotext','-layout',str(pdf),'-'],capture_output=True,text=True,timeout=60,check=True)
        pages=r.stdout.split('\f')
        if pages and not pages[-1].strip(): pages.pop()
        return {'status':'ok','pages':pages,'error':''}
    except (OSError,subprocess.SubprocessError):
        return {'status':'unavailable','pages':[],'error':'extraction_failed'}

def preflight(rows, data, source_paths=None, source_id=None, pdf_path=None, extractor=_pages):
    """Check reported native numeric token(s) occur on claimed physical page.

    `data` is canonical loaded data (sources mapping). Explicit source_id/pdf_path is
    useful for isolated intake tests. Results never establish row/column semantics.
    """
    source_paths=source_paths or {}; cache={}; results=[]
    for row in rows:
        sid=row.get('source_id',source_id or '')
        source=data.get('sources',{}).get(sid)
        ev=row.get('evidence',{})
        base={'observation_id':row.get('observation_id',''),'source_id':sid,'page':ev.get('page') if isinstance(ev,dict) else None}
        if not isinstance(ev,dict):
            results.append(dict(base,status='mismatch',reason='invalid_evidence'));continue
        if not isinstance(source,dict):
            results.append(dict(base,status='unavailable',reason='unknown_source'));continue
        expected=source.get('sha256'); registered_pages=source.get('page_count')
        if not isinstance(expected,str) or re.fullmatch(r'[a-f0-9]{64}',expected) is None:
            results.append(dict(base,status='unavailable',reason='invalid_registered_hash'));continue
        if type(registered_pages) is not int or registered_pages<=0:
            results.append(dict(base,status='unavailable',reason='invalid_registered_page_count'));continue
        if source.get('locator_kind')!='pdf':
            results.append(dict(base,status='unavailable',reason='registered_source_not_pdf'));continue
        raw=pdf_path if source_id and sid==source_id and pdf_path else source_paths.get(sid)
        if not raw:
            results.append(dict(base,status='unavailable',reason='local_path_unresolved'));continue
        try:
            path=Path(raw)
            if not _allowed(path): results.append(dict(base,status='unavailable',reason='protected_path'));continue
            if not path.is_file(): results.append(dict(base,status='unavailable',reason='local_path_missing'));continue
        except (OSError,TypeError):
            results.append(dict(base,status='unavailable',reason='local_path_unavailable'));continue
        if sid not in cache:
            try:
                actual=digest(path)
            except (OSError, PermissionError):
                cache[sid]={'status':'unavailable','reason':'local_read_failed'}
            else:
                if actual!=expected: cache[sid]={'status':'unavailable','reason':'hash_mismatch'}
                else:
                    try:
                        v=extractor(path)
                    except (OSError, PermissionError, subprocess.SubprocessError):
                        v={'status':'unavailable','pages':[],'error':'extraction_failed'}
                    v['expected_page_count']=registered_pages;cache[sid]=v
        item=cache[sid]
        if item['status']!='ok': results.append(dict(base,status='unavailable',reason=item.get('reason',item.get('error','extraction_failed'))));continue
        if isinstance(item.get('expected_page_count'),int) and item['expected_page_count']!=len(item['pages']):
            results.append(dict(base,status='mismatch',reason='registered_page_count_mismatch',extracted_page_count=len(item['pages']),registered_page_count=item['expected_page_count']));continue
        page=base['page']; pages=item['pages']
        if type(page) is not int or page<1 or page>len(pages): results.append(dict(base,status='mismatch',reason='page_out_of_extracted_range',extracted_page_count=len(pages),registered_page_count=item.get('expected_page_count')));continue
        # A scanned page carries no text layer, so no token can be found on it. Reporting that as a
        # missing value would read as evidence against the row; the truth is the check cannot reach it.
        if not pages[page-1].strip():
            results.append(dict(base,status='unavailable',reason='page_has_no_text_layer',extracted_page_count=len(pages),registered_page_count=item.get('expected_page_count')));continue
        tokens=numeric_tokens(pages[page-1]); wanted=[]
        try:
            wanted=[Decimal(ev['reported_value'])]
            if 'reported_upper_value' in ev:wanted.append(Decimal(ev['reported_upper_value']))
            if not all(v.is_finite() for v in wanted):raise ValueError('nonfinite')
        except (InvalidOperation,ValueError,TypeError,KeyError): results.append(dict(base,status='mismatch',reason='invalid_native_value'));continue
        missing=[str(x) for x in wanted if x not in tokens]
        # A value the source line-wraps inside a narrow cell is on the page but never contiguous in
        # extracted text, in any pdftotext mode. Where the evidence declares the on-page fragments,
        # confirm them literally and in order rather than reporting a false absence.
        wrap_confirmed=False
        if missing and isinstance(ev.get('page_wrapped_fragments'),list):
            from .evidence import wrapped_fragments_value,_thousands
            fragments=ev['page_wrapped_fragments']
            if all(isinstance(f,str) and f for f in fragments):
                declared={_thousands(v) for v in [ev.get('reported_value'),ev.get('reported_upper_value')] if v is not None}
                if wrapped_fragments_value(fragments) in declared:
                    page_text=pages[page-1];cursor=0;ordered=True
                    for f in fragments:
                        found=page_text.find(f,cursor)
                        if found<0:ordered=False;break
                        cursor=found+len(f)
                    if ordered:
                        wrap_confirmed=True
                        missing=[m for m in missing if _thousands(m)!=wrapped_fragments_value(fragments)]
        # A compound the source prints as scaled pieces (4,428億24百万円) has no single token on the
        # page. Confirm each declared piece literally and in order instead of reporting an absence.
        compound_confirmed=False
        if missing and isinstance(ev.get('page_compound_scaled_parts'),list):
            parts=ev['page_compound_scaled_parts']
            if all(isinstance(p,dict) and isinstance(p.get('value'),str) and p['value'] for p in parts):
                page_text=pages[page-1];cursor=0;ordered=True
                for p in parts:
                    found=-1
                    for form in (p['value'],_thousands_text(p['value'])):
                        at=page_text.find(form,cursor)
                        if at>=0 and (found<0 or at<found):found=at;matched=form
                    if found<0:ordered=False;break
                    cursor=found+len(matched)
                if ordered:
                    compound_confirmed=True;missing=[]
        entry=dict(base,status='pass' if not missing else 'mismatch',reason='' if not missing else 'native_token_absent',missing_native_values=missing,extracted_page_count=len(pages),registered_page_count=item.get('expected_page_count'))
        if wrap_confirmed:entry['reason']=entry['reason'] or 'page_wrapped_fragments_confirmed'
        if compound_confirmed:entry['reason']=entry['reason'] or 'page_compound_scaled_parts_confirmed'
        results.append(entry)
    return results
