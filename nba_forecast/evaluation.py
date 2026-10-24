"""Matched-sample probability comparisons and favorite calibration summaries."""
import hashlib
import json
import math

from .model import timestamp
from .replay import metrics


def sample_identity(row):
    return {'game_id': str(row['game_id']), 'start': timestamp(row['start']).isoformat(),
            'home': row['home'], 'away': row['away'], 'home_win': row['home_win'],
            'cutoff': timestamp(row['forecast_cutoff']).isoformat(),
            'eligible': bool(row['eligible_for_evaluation']),
            'availability_policy': row.get('forecast_policy_version',row.get('kind','unspecified')),
            'source_data_sha256': row.get('source_data_sha256')}


def compare_samples(samples, established=False, baseline='base'):
    """Reject mismatches BEFORE applying the shared, predeclared window."""
    if baseline not in samples or len(samples) < 2:
        raise ValueError('A baseline and at least one candidate are required')
    lookup = {}
    for name, rows in samples.items():
        lookup[name] = {}
        for row in rows:
            identity = sample_identity(row)
            identifier = identity['game_id']
            if identifier in lookup[name]:
                raise ValueError(f'Duplicate game in {name}: {identifier}')
            if identity['home_win'] not in (0, 1) or timestamp(row['forecast_cutoff']) >= timestamp(row['start']):
                raise ValueError('Invalid outcome or non-pregame cutoff')
            p, q = row['home_probability'], row['away_probability']
            if not all(isinstance(x, (float, int)) and math.isfinite(x) and 0 <= x <= 1 for x in [p, q]) or abs(p+q-1) > 1e-12:
                raise ValueError(f'Missing or invalid probability in {name}: {identifier}')
            lookup[name][identifier] = (identity, row)
    reference = lookup[baseline]
    for name, values in lookup.items():
        if set(values) != set(reference):
            raise ValueError(f'Sample mismatch for {name}; missing {len(set(reference)-set(values))}, extra {len(set(values)-set(reference))}')
        if any(values[key][0] != reference[key][0] for key in reference):
            raise ValueError(f'Outcome, cutoff, teams, start or eligibility differs for {name}')
    ids = sorted(key for key, (identity, _) in reference.items() if not established or identity['eligible'])
    identities = [reference[key][0] for key in ids]
    fingerprint = hashlib.sha256(json.dumps(identities, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    scores = {name: metrics([values[key][1] for key in ids]) for name, values in lookup.items()}
    base = scores[baseline]
    deltas = {name: {key: (score[key]-base[key] if score['games'] else None)
                     for key in ['log_loss', 'brier_score', 'winner_accuracy']} for name, score in scores.items()}
    return {'games': len(ids), 'game_ids': ids, 'sample_sha256': fingerprint, 'baseline': baseline,
            'window': 'ten_prior_games_each' if established else 'all_games_including_openers',
            'metrics': scores, 'difference_from_baseline': deltas,
            'policy': 'Exact same game IDs, outcomes, pregame cutoffs and eligibility; no silent intersection.'}


def compare_variants(rows, established=False):
    samples = {}
    for variant in ['base', 'injury', 'boosted']:
        samples[variant] = []
        for row in rows:
            if variant not in row.get('probability_models', {}):
                raise ValueError(f'Missing {variant} forecast for {row["game_id"]}')
            samples[variant].append({**row, **row['probability_models'][variant]})
    return compare_samples(samples, established=established)


def favorite_bands(rows):
    """Five-percentage-point bins of the predicted FAVORITE, not home team."""
    buckets = {i: [] for i in range(10, 20)}
    for row in rows:
        p = row.get('home_probability')
        if p is None:
            continue
        if not math.isfinite(p) or not 0 <= p <= 1 or row['home_win'] not in (0, 1):
            raise ValueError('Invalid calibration row')
        confidence = max(p, 1-p)
        # Round only for bucket placement at decimal boundaries (e.g. 0.60).
        index = min(19, int(math.floor(round(confidence*20, 10))))
        buckets[index].append((confidence, int((p >= .5) == bool(row['home_win']))))
    output = []
    for index, values in buckets.items():
        if not values:
            continue
        n = len(values); wins = sum(v[1] for v in values); rate = wins/n
        z = 1.959963984540054; denominator = 1+z*z/n
        center = (rate+z*z/(2*n))/denominator
        radius = z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/denominator
        output.append({'band': f'{index*5}–{(index+1)*5}%', 'games': n, 'wins': wins,
                       'mean_forecast': sum(v[0] for v in values)/n, 'observed_win_rate': rate,
                       'lower_95': center-radius, 'upper_95': center+radius})
    return output
