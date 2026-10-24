"""Reproduce the research-only rating quality experiment; never publish forecasts."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.rating_quality import (apply_heads, fit_heads, paired_intervals, parameters,
                                        rating_scores, replay_seasons)
from nba_forecast.evaluation import compare_samples, favorite_bands

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT/'experiments/rating-quality-v1'


def compact_summary(result):
    """Keep matched fingerprints and all metrics; full IDs/rows regenerate locally."""
    import copy
    summary = copy.deepcopy(result)
    comparisons = [summary['comparison'], summary['established_comparison']]
    comparisons += [fold['comparison'] for fold in summary['folds']]
    for comparison in comparisons:
        comparison.pop('game_ids')
        for score in comparison['metrics'].values():
            score.pop('calibration', None)
    return summary


def run(output):
    manifest = json.loads((STUDY/'inputs.json').read_text())
    seasons = {}
    for season, expected in manifest['source_sha256'].items():
        raw = (ROOT/'data/seasons'/season/'games.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f'Source snapshot changed: {season}; version a new experiment')
        seasons[season] = json.loads(raw)
    samples = {key: [] for key in ['original_raw', 'independent_lead_raw', 'original_common_head', 'independent_lead_common_head']}
    folds, heads = [], {}
    for year in [2024, 2025, 2026]:
        season = f'{year-1}-{str(year)[-2:]}'
        prefix = {s: games for s, games in seasons.items() if s <= season}
        fold = {}
        for family in ['original', 'independent_lead']:
            path = STUDY/'fits'/f'{family}_{year-1}.json'
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != manifest['fit_sha256'][path.name]:
                raise ValueError(f'Fit changed: {path.name}')
            fit = json.loads(raw)
            train_year = fit.get('training_end_year', fit.get('year'))
            if train_year != year-1 or not fit.get('converged'):
                raise ValueError('Invalid earlier-prefix fit')
            challenger = family == 'independent_lead'
            rows = replay_seasons(prefix, parameters(fit, challenger), fit['vector'][4] if challenger else None)
            train = [r for r in rows if r['season'] < season]
            test = [r for r in rows if r['season'] == season]
            head = fit_heads(train); heads[f'{season}/{family}'] = head
            calibrated = apply_heads(test, head)
            raw_rows = [{**r, 'predicted_margin': q['predicted_margin']} for r, q in zip(test, calibrated)]
            for suffix, selected in [('raw', raw_rows), ('common_head', calibrated)]:
                key = f'{family}_{suffix}'
                for r in selected:
                    r['source_data_sha256'] = manifest['source_sha256'][season]
                fold[key] = selected; samples[key].extend(selected)
        folds.append({'season': season, 'comparison': compare_samples(fold, baseline='original_raw'),
                      'rating_scores': {key: rating_scores(rows) for key, rows in fold.items()}})
        print('Evaluated', season, len(test), 'games', flush=True)
    result = {'status': 'Retrospective exploratory; outcomes previously inspected; no production promotion',
              'protocol': 'experiments/rating-quality-v1/PROTOCOL.md',
              'inputs': manifest, 'folds': folds,
              'comparison': compare_samples(samples, baseline='original_raw'),
              'established_comparison': compare_samples(samples, established=True, baseline='original_raw'),
              'rating_scores': {key: rating_scores(rows) for key, rows in samples.items()},
              'favorite_calibration': {key: favorite_bands(rows) for key, rows in samples.items()},
              'paired_intervals': {
                  'raw_independent_minus_original': paired_intervals(samples['independent_lead_raw'], samples['original_raw']),
                  'common_head_independent_minus_original': paired_intervals(samples['independent_lead_common_head'], samples['original_common_head'])},
              'heads': heads,
              'code_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [Path(__file__), ROOT/'experiments/rating_quality.py', STUDY/'PROTOCOL.md']},
              'market_evaluation': 'Not performed: no timestamped executable odds supplied; no ROI claim.'}
    output.mkdir(parents=True, exist_ok=True)
    (output/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    with (output/'predictions.csv').open('w', newline='') as handle:
        fields = ['family', 'game_id', 'season', 'date', 'forecast_cutoff', 'start', 'home_id', 'away_id', 'home', 'away',
                  'home_rating', 'away_rating', 'home_probability', 'away_probability', 'home_win', 'margin',
                  'predicted_margin', 'eligible_for_evaluation', 'source_data_sha256']
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for family, rows in samples.items():
            writer.writerows({'family': family, **r} for r in rows)
    summary = compact_summary(result)
    (output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    for key, score in result['comparison']['metrics'].items():
        print(key, {k: score[k] for k in ['games', 'log_loss', 'brier_score', 'winner_accuracy']}, result['rating_scores'][key], flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=STUDY/'results')
    run(parser.parse_args().output)
