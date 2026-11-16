"""Numeric excerpt and exact native-unit consistency, not source corroboration."""
import re
from decimal import Decimal

# Match whole signed decimal tokens, never digit substrings. Full-width punctuation
# is normalized before matching; unrelated table tokens are not column resolution.
_NUMBER=r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
# A trailing period is sentence punctuation unless a digit follows it, so '390.' at the end of a
# clause must still tokenise. Rejecting any trailing '.' made every sentence-final numeral invisible
# and produced false 'value absent from excerpt' failures.
TOKEN=re.compile(r'(?<![\d.])(?:\(\s*-?'+_NUMBER+r'\s*\)|-?'+_NUMBER+r')(?!\d|\.\d)')

def arabic_tokens(excerpt):
    """Treat a complete numeric accounting parenthesis as a negative token."""
    text=excerpt.translate(str.maketrans({'，':',','−':'-','－':'-','（':'(', '）':')'}))
    values=set()
    for match in TOKEN.finditer(text):
        token=match.group().replace(',','')
        values.add(-abs(Decimal(token[1:-1].strip())) if token.startswith('(') else Decimal(token))
    return values

def lexical_mems_lines(excerpt):
    """Recognize the reviewed affirmative line-count clause, not general numerals."""
    text = re.sub(r'\s+', '', excerpt)
    clause = r'(?:三条8寸MEMS产线|一条12寸MEMS产线)'
    pattern = r'(?:^|[。；;，,])目前已拥有(' + clause + r'(?:和' + clause + r')*)(?=$|[。；;，,])'
    bindings = []
    for match in re.finditer(pattern, text):
        for part in match.group(1).split('和'):
            bindings.append((Decimal(3), '8_inch') if part.startswith('三')
                            else (Decimal(1), '12_inch'))
    return bindings

def lexical_equipment_counts(excerpt):
    """Bind narrowly reviewed Chinese thousand clauses to measure/unit/qualifier.

    数千 and 千台级 remain qualitative. This is not a general numeral parser.
    Reject negative, conditional and projected clauses; original semantic review
    still establishes the product population and reporting date.
    """
    text = re.sub(r'\s+', '', excerpt)
    bindings = []
    for clause in re.split(r'[。；;，,]', text):
        if re.search(r'未|不|无|没有|尚|预计|计划|目标|将|有望|若|假设', clause):
            continue
        if re.search(r'累计出货近千腔$', clause):
            bindings.append((Decimal(1000), 'chamber', 'approaching', 'cumulative_shipments'))
        if re.search(r'累计交付量(?:均)?突破千台$', clause):
            bindings.append((Decimal(1000), 'system', 'gt', 'cumulative_equipment_deliveries'))
    return bindings

_CN_DIGIT={'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
_CN_UNIT={'十':10,'百':100,'千':1000}
_CN_VAGUE=re.compile(r'[数几多]\s*[十百千万]')
_EN_CARD={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,
 'eleven':11,'twelve':12,'fifteen':15,'twenty':20,'thirty':30,'fifty':50,'hundred':100,
 'first':1,'second':2,'third':3}

def _parse_cn_cardinal(s):
    """Parse a plain Chinese cardinal such as 二十, 三百, 一千五百. None if not one."""
    if not s or any(ch not in _CN_DIGIT and ch not in _CN_UNIT for ch in s):return None
    section=0;digit=None
    for ch in s:
        if ch in _CN_DIGIT:digit=_CN_DIGIT[ch]
        else:
            section+=(digit if digit is not None else 1)*_CN_UNIT[ch];digit=None
    total=section+(digit or 0)
    return Decimal(total) if total>0 else None

def lexical_cardinals(excerpt):
    """Bind plainly written cardinals so a standardised numeric value stays auditable.

    Only simple counts: 二十 -> 20, 三百 -> 300, "two tools" -> 2. Vague magnitude words
    (数百, 几十, 千台级) are excluded and stay qualitative, as do negative, conditional and
    projected clauses. The excerpt is never rewritten: this lets the stored value be a digit
    while the source wording is preserved verbatim.
    """
    text=re.sub(r'\s+','',excerpt);values=set()
    for clause in re.split(r'[。；;，,]',text):
        if re.search(r'未|不|无|没有|尚|预计|计划|目标|将|有望|若|假设',clause):continue
        if re.search(r'级',clause):continue
        for m in re.finditer(r'[零一二两三四五六七八九十百千]{1,6}',clause):
            if m.start() and clause[m.start()-1] in '数几多':continue
            if _CN_VAGUE.search(clause[max(0,m.start()-1):m.end()+1]):continue
            token=m.group(0)
            # A bare unit word is a magnitude, not a count: 千腔 and 百亿元 stay qualitative unless the
            # source writes an explicit digit, as in 三百 or 二十. The narrow reviewed bindings own those.
            if not any(ch in _CN_DIGIT for ch in token):continue
            v=_parse_cn_cardinal(token)
            if v is not None:values.add(v)
    low=excerpt.lower()
    if not re.search(r'\b(?:several|dozens|scores|approximately|plan|expect|target|intend)\b',low):
        for w,v in _EN_CARD.items():
            if re.search(r'\b'+w+r'\b',low):values.add(Decimal(v))
    return values

def numeric_tokens(excerpt):
    text=excerpt
    values=arabic_tokens(excerpt)
    values.update(value for value, _ in lexical_mems_lines(excerpt))
    values.update(binding[0] for binding in lexical_equipment_counts(excerpt))
    values.update(lexical_cardinals(excerpt))
    if re.search(r'(?<![数几未不])超(?:过)?百亿元',text):values.add(Decimal(100))
    return values


def _thousands(value):
    """Render a decimal string the way a filing prints it, for fragment reassembly."""
    text=str(value).strip();sign='-' if text.startswith('-') else ''
    text=text.lstrip('+-');whole,_,frac=text.partition('.')
    return sign+'{:,}'.format(int(whole or 0))+(('.'+frac) if frac else '')

def wrapped_fragments_value(fragments):
    """Reassemble a line-wrapped cell into the number the source prints.

    Concatenation only: the fragments are the characters as they appear on the page,
    so this cannot invent a digit the source did not print.
    """
    return ''.join(fragments)

def compound_parts_total(parts,units,require,oid):
    """Sum a compound the source prints as scaled pieces, e.g. 4,428億24百万円.

    Every piece is a literal page token and carries its own printed unit, so this
    can only add up what the source already wrote; it cannot invent a magnitude.
    """
    from decimal import Decimal
    total=Decimal(0);base=None
    for part in parts:
        unit=part['unit']
        require(unit in units,f'{oid}: unknown compound part unit {unit}')
        definition=units[unit]
        if base is None:base=definition['base_unit']
        require(definition['base_unit']==base,f'{oid}: compound parts mix base units')
        total+=Decimal(str(part['value']).replace(',',''))*Decimal(definition['scale'])
    return total,base


def validate_numeric_evidence(o,data,require,number):
    e=o['evidence'];oid=o['observation_id'];units=data['schema']['x-atlas-units']
    native=number(e['reported_value']);native_unit=e['reported_unit']
    require(native in numeric_tokens(e['excerpt']),f'{oid}: reported value is absent from excerpt numeric tokens')
    fragments=e.get('page_wrapped_fragments')
    if fragments is not None:
        # The declared fragments must reassemble into the printed form of the reported value.
        # This keeps a wrap declaration from standing in for a value the source never prints.
        require(wrapped_fragments_value(fragments)==_thousands(e['reported_value']),
                f'{oid}: declared page fragments do not reassemble into the reported value')
    parts=e.get('page_compound_scaled_parts')
    if parts is not None:
        # A compound declaration must add up to exactly the value the row records, in the row's own
        # unit, so it can never stand in for a figure the source does not actually state.
        total,base=compound_parts_total(parts,units,require,oid)
        require(units[native_unit]['base_unit']==base,f'{oid}: compound parts do not share the reported unit base')
        require(total==native*Decimal(units[native_unit]['scale']),
                f'{oid}: declared compound parts do not sum to the reported value')

    arabic=arabic_tokens(e['excerpt'])
    if native not in arabic:
        if native == 1000:
            binding = (native, native_unit, o['relation'], o['metric_id'])
            require(binding in lexical_equipment_counts(e['excerpt'])
                    and native_unit == o['unit'] and o['period']['basis'] == 'cumulative',
                    f'{oid}: lexical equipment count requires matching measure, unit, qualifier and cumulative basis')
        elif native == 100:
            require(e['reported_unit']=='CNY_100m' and o['relation']=='gt',f'{oid}: lexical Chinese hundred statement requires its explicit greater-than relation')
        else:
            binding = (native, o['dimensions'].get('wafer_line_size'))
            require(o['metric_id']=='internal_mems_production_line_count'
                    and native_unit==o['unit']=='production_line' and o['relation']=='eq'
                    and o['period']['basis']=='period_status'
                    and lexical_mems_lines(e['excerpt']).count(binding)==1,
                    f'{oid}: lexical MEMS line count lacks matching metric, unit, size or affirmative source binding')
    require(native_unit in units and o['unit'] in units,f'{oid}: undeclared evidence unit')
    source=units[native_unit];target=units[o['unit']]
    require(source['base_unit']==target['base_unit'],f'{oid}: source and stored unit dimensions differ')
    factor=number(source['scale'])/number(target['scale'])
    conversion=e.get('conversion')
    if conversion and conversion.get('sign_basis')=='source_reported_decrease':
        from .schema import source_decrease_metric
        require(source_decrease_metric(data['metrics'][o['metric_id']],data['schema'],require),f'{oid}: metric is not declared for source-direction changes')
        require(native>=0 and o['relation'] in {'eq','approx'},f'{oid}: lexical decrease needs a nonnegative native point magnitude and point relation')
        text=e['excerpt'].translate(str.maketrans({'，':','}))
        pattern=r'(?:减少|下降|降低)\s*(约)?\s*('+_NUMBER+r')(?![\d.])'
        matches=[m for m in re.finditer(pattern,text) if number(m.group(2).replace(',',''))==native]
        require(bool(matches),f'{oid}: signed decrease lacks matching source direction and magnitude')
        relation='approx' if any(m.group(1) for m in matches) else 'eq'
        require(o['relation']==relation,f'{oid}: decrease relation differs from source wording')
        factor=-factor
    if conversion and conversion.get('sign_basis')=='source_reported_loss':
        from .schema import source_loss_metric
        require(source_loss_metric(data['metrics'][o['metric_id']],data['schema'],require),f'{oid}: metric is not declared for source-worded losses')
        require(native>=0 and o['relation'] in {'eq','approx'},f'{oid}: lexical loss needs a nonnegative native point magnitude and point relation')
        text=e['excerpt'].translate(str.maketrans({'，':','}))
        # Narrow supported wording: loss immediately governs its printed magnitude.
        # This is a transcription guard, not a general semantic/negation parser.
        pattern=r'(?<![不无未非])(?<!不是)(?:损失|亏损)\s*(约)?\s*('+_NUMBER+r')(?![\d.])'
        negated_prefix=re.compile(r'(?:没有|不存在|未(?:曾)?(?:发生|产生|出现|确认|录得|造成|形成)?|不(?:曾|会|可能)?(?:发生|产生|出现|确认|录得|构成)?|无|并非|不是)(?:任何|重大|明显|实质性|实际|相关|预期)*\s*$')
        matches=[m for m in re.finditer(pattern,text)
                 if number(m.group(2).replace(',',''))==native
                 and not negated_prefix.search(text[:m.start()])]
        require(bool(matches),f'{oid}: signed loss lacks matching non-negated source wording and magnitude')
        relation='approx' if any(m.group(1) for m in matches) else 'eq'
        require(o['relation']==relation,f'{oid}: loss relation differs from source wording')
        factor=-factor
    require(native*factor==number(o['value']),f'{oid}: native value/unit does not resolve to stored value')
    if native_unit!=o['unit']:
        require(conversion is not None,f'{oid}: scaled source value needs a recorded conversion')
    if conversion is not None:
        require(conversion['operation']=='multiply' and number(conversion['factor'])==factor,f'{oid}: conversion factor differs from unit scale')
    if o['relation']=='range':
        require('reported_upper_value' in e,f'{oid}: range needs a native upper value')
        upper=number(e['reported_upper_value'])
        require(upper in numeric_tokens(e['excerpt']),f'{oid}: upper value absent from excerpt')
        require(upper*factor==number(o['upper_value']),f'{oid}: native upper value differs from stored bound')
    else:require('reported_upper_value' not in e,f'{oid}: upper evidence requires range relation')
    source_record=data['sources'][o['source_id']]
    # 'chart_data' marks a series transcribed from a published chart's underlying data where the report
    # itself is not held. The value/excerpt arithmetic still applies, but no original-passage or physical
    # page check is possible, so it is only permitted for the reference tier.
    require(source_record.get('locator_kind') in {'pdf','html','chart_data'},f'{oid}: source locator kind missing')
    if source_record.get('locator_kind')=='chart_data':
        require(data['datasets'][source_record['dataset_id']]['status']=='reference_only',
                f'{oid}: chart_data locators are limited to the reference tier')
    require(type(source_record.get('page_count')) is int and source_record['page_count']>0,f'{oid}: source page count missing')
    require(e['page']<=source_record['page_count'],f'{oid}: physical page exceeds source page count')
