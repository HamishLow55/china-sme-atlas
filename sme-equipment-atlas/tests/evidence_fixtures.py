"""Explicit synthetic evidence for tests that change values; never production data."""
def bind_synthetic(row):
    e=row['evidence']
    e.update(reported_value=row['value'],reported_unit=row['unit'],excerpt='SYNTHETIC TEST ONLY: '+row['value']+' '+row['unit'])
    e.pop('conversion',None);e.pop('reported_upper_value',None)
    row.pop('conversion_audit',None)
    if row['relation']=='range':
        e['reported_upper_value']=row['upper_value'];e['excerpt']+=' to '+row['upper_value']
    return row
