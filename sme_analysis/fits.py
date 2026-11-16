"""Small fitting helpers for derived analyses in the tool reports: adoption S-curves, growth rates, and a writer for
chart data files. Numpy only. Every fit here is a model, not evidence: cite its output as a `derived` ledger row whose
locator lists the input claims, and say in the text how sensitive the answer is to the assumptions.

    from sme_analysis.fits import logistic_fit, cagr, write_series
    f = logistic_fit([2019, 2021, 2023, 2025], [0.02, 0.06, 0.15, 0.31], K=1)   # a share saturating at 100%
    f['t50'], f['band'](2030)                                                   # midpoint year; low/high at 2030
"""
import csv
import math
from pathlib import Path
import numpy as np

def _linfit(t, z):
    """Least squares z = a + b t; returns (a, b)."""
    b, a = np.polyfit(t, z, 1)
    return a, b

def logistic(t, K, r, t0):
    """K / (1 + exp(-r (t - t0)))."""
    return K/(1+np.exp(-r*(np.asarray(t, float)-t0)))

def logistic_fit(t, y, K=None, K_range=None, grid=200, tolerance=1.5):
    """Fit y = K / (1 + exp(-r (t - t0))) to points (t, y), all y > 0.

    K: the ceiling, if known (e.g. 1 for a share, or a market size); otherwise it is profiled over K_range
    (default max(y)*1.05 to max(y)*10) and the best fit kept. With few points the ceiling is weakly identified,
    which is the main uncertainty: every K whose squared error is within `tolerance` x the best is kept, and `band`
    returns the low and high curves across them. Report that band, not just the central curve.

    Returns {'K', 'r', 't0', 't50', 'sse', 'r2', 'n', 'curve': f(t), 'band': f(t) -> (low, high), 'Ks': kept ceilings}.
    """
    t = np.asarray(t, float); y = np.asarray(y, float)
    if len(t) < 3: raise ValueError('a logistic fit needs at least three points')
    if (y <= 0).any(): raise ValueError('logistic fits need positive values')
    def fit_at(k):
        if k <= y.max(): return None
        z = np.log(y/(k-y)); a, b = _linfit(t, z)
        if b <= 0: return None
        r, t0 = b, -a/b; sse = float(((logistic(t, k, r, t0)-y)**2).sum())
        return {'K': float(k), 'r': float(r), 't0': float(t0), 'sse': sse}
    if K is not None:
        cands = [fit_at(float(K))]
        if cands[0] is None: raise ValueError(f'K={K} must exceed every y and give a rising curve')
    else:
        lo, hi = K_range or (y.max()*1.05, y.max()*10)
        cands = [c for c in (fit_at(k) for k in np.geomspace(lo, hi, grid)) if c]
        if not cands: raise ValueError('no rising logistic fits the points in K_range')
    best = min(cands, key=lambda c: c['sse'])
    kept = [c for c in cands if c['sse'] <= best['sse']*tolerance + 1e-12]
    ss_tot = float(((y-y.mean())**2).sum()) or 1e-12
    curve = lambda x, c=best: logistic(x, c['K'], c['r'], c['t0'])
    def band(x):
        vals = np.array([logistic(x, c['K'], c['r'], c['t0']) for c in kept])
        return vals.min(axis=0), vals.max(axis=0)
    return {**best, 't50': best['t0'], 'r2': 1-best['sse']/ss_tot, 'n': len(t), 'curve': curve, 'band': band,
            'Ks': [c['K'] for c in kept]}

def years_to(f, level):
    """Year at which a fitted logistic reaches `level` (in y units); None if it never does."""
    if level >= f['K']: return None
    return f['t0'] - math.log(f['K']/level-1)/f['r']

def cagr(v0, v1, years):
    """Compound annual growth rate between two values `years` apart."""
    return (v1/v0)**(1/years)-1

def write_series(path, periods, values, claim_id, low=None, high=None, relation='approx'):
    """Write a chart data file (period,value,low,high,relation,claim_id) for a derived series."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    low = low if low is not None else [None]*len(values); high = high if high is not None else [None]*len(values)
    r = lambda v: '' if v is None or (isinstance(v, float) and math.isnan(v)) else f'{float(v):.6g}'
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['period', 'value', 'low', 'high', 'relation', 'claim_id'])
        for p, v, l, h in zip(periods, values, low, high): w.writerow([p, r(v), r(l), r(h), relation, claim_id])
