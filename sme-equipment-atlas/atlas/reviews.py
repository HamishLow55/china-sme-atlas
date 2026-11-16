"""Small, claim-linked current sweep reviews; historical archives are immutable."""
import json
from datetime import date
from .core import require, valid_date

FIELDS = {'reviewer', 'date', 'source_ids', 'observation_ids', 'decisions', 'holds', 'limitations'}
MAX_BYTES = 50_000

def validate_reviews(data, root):
    for path in (root / 'docs/reviews').glob('*.json'):
        require(path.stat().st_size <= MAX_BYTES, f'{path.name}: review exceeds 50 KB')
        row = json.loads(path.read_text())
        require(set(row) == FIELDS, f'{path.name}: review must use the fixed sweep shape')
        require(path.stem.endswith('_sweep'), f'{path.name}: use one record per named sweep')
        reviewers = data['schema']['properties']['evidence']['properties']['reviewer']['enum']
        require(row['reviewer'] in reviewers and row['reviewer'], 'Undeclared review author')
        valid_date(row['date'])
        require(date.fromisoformat(row['date']) <= date.today(), 'Future sweep review date')
        for field, registry in [('source_ids', 'sources'), ('observation_ids', 'observations')]:
            require(isinstance(row[field], list) and len(row[field]) == len(set(row[field])), f'Invalid {field}')
            require(set(row[field]) <= set(data[registry]), f'Unknown review {field}')
        require(isinstance(row['decisions'], dict), 'Review decisions must map claim IDs to dispositions')
        require(set(row['decisions']) == set(row['observation_ids']), 'Each reviewed observation needs a decision')
        require(all(isinstance(x, str) and x for x in row['decisions'].values()), 'Review decisions must be text, not copied observations')
        require(all(data['observations'][oid]['source_id'] in row['source_ids'] for oid in row['observation_ids']), 'Review source set does not cover its claims')
        for field in ('holds', 'limitations'):
            require(isinstance(row[field], list) and all(isinstance(x, str) for x in row[field]), f'Invalid review {field}')
