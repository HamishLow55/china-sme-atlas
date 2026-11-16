"""Currency conversion to USD at Eurostat annual-average rates (sme_analysis/fx_per_eur.csv; data, not a judgement table).

Flows (revenue, spending) use the period's annual average; 2026 uses the year-to-date mean of monthly averages.
Years after the table's last use its latest rate (forecasts). Quarterly and half-year figures use their year's annual average, which is close enough for charts and text but
not for precise quarter-on-quarter work. Balance-sheet stocks should strictly use period-end rates; say so where
it matters.

    from sme_analysis.fx import usd
    usd(1234, 'CNY', 2025)          # -> USD equivalent, same scale as the input
    usd(5.2, 'JPY', '2024 H1')      # period labels work: '2024 H1', '2024-06', 'FY2024', 'FY24'
"""
import re
from functools import lru_cache
import pandas as pd
from pathlib import Path
TABLE = Path(__file__).with_name('fx_per_eur.csv')

UNIT = re.compile(r'^\s*(CNY|RMB|USD|JPY|KRW|EUR|TWD|HKD)\s*(k|10k|m|100m|bn)?\s*$',re.I)
# scale suffix -> (multiplier, USD unit). 10k and 100m are the Chinese 万 and 亿 units.
SCALE = {'':(1,'USD'),'k':(1,'USD k'),'10k':(10,'USD k'),'m':(1,'USD m'),'100m':(100,'USD m'),'bn':(1000,'USD m')}
YEAR = re.compile(r'(?<!\d)(20\d\d)(?!\d)|FY(\d\d)(?!\d)',re.I)

@lru_cache(maxsize=None)
def _table():
    t=pd.read_csv(TABLE,dtype={'year':str})
    return {(r.currency,r.year):float(r.units_per_eur) for r in t.itertuples()}

def year_of(period):
    """Calendar year for a period label: 2025, '2025 H1', '2025-06', 'FY2024', 'FY20'. Japanese fiscal years (April
    start) take their label year, which covers nine of their twelve months."""
    m=YEAR.search(str(period))
    if not m:raise KeyError(f'no year in period {period!r}')
    return m.group(1) or '20'+m.group(2)

def usd_per_unit(currency, period):
    """USD per one unit of `currency` in the year of `period`."""
    cur=currency.upper().replace('RMB','CNY');year=year_of(period)
    if cur=='USD':return 1.0
    t=_table();last=max(y for _,y in t)
    if year>last:year=last  # forecasts and future periods use the latest (year-to-date) rate
    usd=t.get(('USD',year));per=1.0 if cur=='EUR' else t.get((cur,year))
    if usd is None or per is None:raise KeyError(f'no FX rate for {cur} in {year}; sme_analysis/fx_per_eur.csv covers 2015-2026')
    return usd/per

def usd(value, currency, period):
    return None if value is None else value*usd_per_unit(currency,period)

def parse_money_unit(unit):
    """(currency, multiplier, USD unit) for money units such as 'CNY m', 'JPY bn', 'CNY 100m', 'CNY'; else None.
    'CNY bn' -> ('CNY', 1000, 'USD m'): multiply the value, convert, and label it in the USD unit."""
    m=UNIT.match(unit or '')
    if not m:return None
    k,out=SCALE[(m.group(2) or '').lower()]
    return (m.group(1).upper().replace('RMB','CNY'),k,out)
