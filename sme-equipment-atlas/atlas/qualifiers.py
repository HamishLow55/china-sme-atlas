"""Positive-scale interval arithmetic, with unquantified approximation retained."""
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from .core import number, require


def interval(observation,scale=Decimal(1)):
    value=number(observation['value'])*scale;relation=observation['relation']
    require(value>=0,'Ratio inputs must be nonnegative')
    require(not (relation=='eq' and observation.get('precision') in {'bounded_as_reported','reported_lower_bound'}),'Bounded precision requires an explicit relation before ratio calculation')
    approximate=relation in {'approx','approaching'} or observation.get('precision') in {'approximate','rounded','as_reported_rounded'}
    lower=upper=value;lower_closed=upper_closed=True
    if relation in {'gt','ge'}:upper=None;lower_closed=relation=='ge';upper_closed=False
    elif relation in {'lt','le'}:lower=Decimal(0);upper_closed=relation=='le'
    elif relation=='range':
        upper=number(observation['upper_value'])*scale
        require(upper>=lower,'Reversed ratio input range')
    else:require(relation in {'eq','approx','approaching'},'Unsupported ratio qualifier')
    require(upper is None or upper>lower or (upper==lower and lower_closed and upper_closed),'Empty input interval')
    return {'lower':lower,'upper':upper,'lower_closed':lower_closed,'upper_closed':upper_closed,'approximate':approximate}


def scale_interval(bounds,factor):
    return {**bounds,'lower':bounds['lower']*factor,'upper':None if bounds['upper'] is None else bounds['upper']*factor}


def ratio_interval(n,d):
    require(d['upper'] is None or d['upper']>0,'Nonpositive denominator')
    require(d['lower']>0 or (d['lower']==0 and not d['lower_closed']),'Denominator interval includes zero')
    zero=n['lower']==0 and n['upper']==0
    lower=Decimal(0) if d['upper'] is None else 100*n['lower']/d['upper']
    lower_closed=(n['lower']==0 and n['lower_closed']) or (d['upper'] is not None and n['lower_closed'] and d['upper_closed'])
    upper=Decimal(0) if zero else None if n['upper'] is None or d['lower']==0 else 100*n['upper']/d['lower']
    upper_closed=zero or (upper is not None and n['upper_closed'] and d['lower_closed'])
    return {'lower':lower,'upper':upper,'lower_closed':lower_closed,'upper_closed':upper_closed,'approximate':n['approximate'] or d['approximate']}


def result_fields(bounds):
    """Bounds round outwards; approximate anchors are not confidence intervals."""
    lo,hi=bounds['lower'],bounds['upper'];point=hi==lo and bounds['lower_closed'] and bounds['upper_closed']
    relation=('approx' if bounds['approximate'] else 'eq') if point else ('gt' if not bounds['lower_closed'] else 'ge') if hi is None else 'range'
    quant=Decimal('0.0001')
    lower=lo.quantize(quant,rounding=ROUND_FLOOR);upper=None if hi is None else hi.quantize(quant,rounding=ROUND_CEILING)
    # Rounding an endpoint outward makes it a closed conservative bound.
    lc=bounds['lower_closed'] or lower!=lo;uc=bounds['upper_closed'] or upper!=hi
    if not point and hi is None:relation='ge' if lc else 'gt'
    return {'value':f'{lo:.4f}' if point else None,'relation':relation,'approximate':bounds['approximate'],
            'lower_value':None if point else str(lower),'upper_value':None if point or upper is None else str(upper),
            'lower_inclusive':None if point else lc,'upper_inclusive':None if point or upper is None else uc,
            'uncertainty_note':'Approximation is inherited from the source; no numerical tolerance or confidence interval was inferred.' if bounds['approximate'] else ''}


def display_result(result):
    unit='%' if result['unit']=='percent' else ' '+result['unit']
    if result['value'] is not None:
        value=number(result['value'])
        return ('approximately '+f'{value:.2g}' if result.get('approximate') else f'{value:.2f}')+unit
    lo=result.get('lower_value');hi=result.get('upper_value')
    if lo is None:return ''
    prefix='Approximate bounds: ' if result.get('approximate') else ''
    if hi is None:return prefix+('≥' if result['lower_inclusive'] else '>')+lo+unit
    return prefix+('[' if result['lower_inclusive'] else '(')+lo+', '+hi+(']' if result['upper_inclusive'] else ')')+unit
