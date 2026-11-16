"""Require a deliberate reuse decision before admitting a new metric proposal."""
from .core import require

def validate_metric_proposal(metric, existing, decision):
    mid = metric['metric_id']
    require(isinstance(decision, dict), f'{mid}: new metric needs --metric-decisions reuse review')
    require(set(decision) == {'compared_metric_ids', 'reason', 'semantic_validation'}, f'{mid}: invalid metric reuse review')
    compared = decision['compared_metric_ids']
    require(isinstance(compared, list) and compared and all(x in existing for x in compared), f'{mid}: compare declared existing metrics first')
    require(isinstance(decision['reason'], str) and decision['reason'].strip(), f'{mid}: explain why dimensions or a unit extension cannot express this claim')
    require(decision['semantic_validation'] in {'tested', 'schema_only'}, f'{mid}: declare tested or schema_only semantics')
    for old in existing.values():
        require(metric.get('definition', '').strip() != old.get('definition', '').strip(), f'{mid}: duplicate definition; reuse {old["metric_id"]}')
