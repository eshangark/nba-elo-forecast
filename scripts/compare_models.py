"""Expanding-window retrospective checks of multifactor versus simple Elo."""

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_forecast.benchmark import fit_simple, paired_comparison
from nba_forecast.data import write_json
from nba_forecast.fitting import fit
from nba_forecast.model import Parameters, timestamp
from nba_forecast.replay import replay


def label(year):
    return f'{year-1}-{str(year)[-2:]}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, default=Path('data/seasons'))
    parser.add_argument('--release-model', type=Path, default=Path('models/nba-v0.2'))
    parser.add_argument('--output', type=Path, default=Path('models/comparison-v0.2'))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--maxiter', type=int, default=150)
    args = parser.parse_args()
    seasons, sources = {}, {}
    for year in range(2022, 2027):
        path = args.archives / label(year) / 'games.json'
        raw = path.read_bytes(); games = json.loads(raw)
        if len(games) != 1230 or len({g['game_id'] for g in games}) != 1230:
            raise ValueError(f'Incomplete season {year}')
        seasons[year] = games
        sources[label(year)] = hashlib.sha256(raw).hexdigest()
    release = json.loads((args.release_model / 'fit_report.json').read_text())
    output = {'comparison': 'simple Elo versus multifactor Elo v0.2 family',
              'status': 'retrospective diagnostic; later outcomes already inspected during project development',
              'seed': args.seed, 'formula_or_bounds_changed': False,
              'warmup_games_per_team': 10, 'season_initialization': 1500,
              'cutoff': 'Earlier of 10:00 Eastern and one hour before first tip; prior slates only',
              'source_file_sha256': sources, 'folds': []}
    prediction_rows = []
    for year in range(2023, 2027):
        training_years = list(range(2022, year))
        training = [seasons[y] for y in training_years]
        if max(timestamp(g['start']) for games in training for g in games) >= min(timestamp(g['start']) for g in seasons[year]):
            raise ValueError('Training history overlaps evaluation')
        print(f'Fit through {label(year-1)}; evaluate {label(year)}', flush=True)
        if year == 2025:
            # Reuse the frozen release for precisely the original training split.
            for y in training_years:
                committed = json.loads((args.archives / label(y) / 'snapshot.json').read_text())['result']
                expected = hashlib.sha256(json.dumps(seasons[y], sort_keys=True).encode()).hexdigest()
                if committed['dataset_sha256'] != expected or committed['parameters'] != release['parameters']:
                    raise ValueError('Frozen release/data mismatch')
            full_params, full_report = Parameters(**release['parameters']), release
            origin = 'original frozen release; no refit'
        else:
            full_params, full_report = fit(training, seed=args.seed, maxiter=args.maxiter)
            if not full_report['optimizer_success']:
                raise ValueError('Full-model optimizer did not converge')
            origin = 'training-prefix-only refit; retrospective check'
        simple_params, simple_report = fit_simple(training, seed=args.seed, maxiter=args.maxiter)
        frozen_at = datetime.now(timezone.utc).isoformat()
        write_json(args.output / f'fit_{year}.json', {
            'training_seasons': [label(y) for y in training_years], 'evaluation_season': label(year),
            'frozen_before_fold_evaluation_at': frozen_at, 'full_origin': origin,
            'full_model': full_report, 'simple_elo': simple_report,
        })
        # Evaluation outcomes are excluded from both fitting objectives.
        full = replay(seasons[year], full_params, fitted=True, warmup_games=10)
        simple = replay(seasons[year], simple_params, fitted=True, warmup_games=10)
        comparison = paired_comparison(full['predictions'], simple['predictions'], seed=args.seed)
        fold = {'training_seasons': [label(y) for y in training_years], 'evaluation_season': label(year),
                'full_origin': origin, 'full_parameters': asdict(full_params),
                'simple_parameters': {'k': simple_params.k, 'home_advantage': simple_params.home_advantage, 'c': simple_params.c},
                'full_metrics': full['metrics'], 'simple_metrics': simple['metrics'], 'paired_comparison': comparison}
        output['folds'].append(fold)
        for a, b in zip(full['predictions'], simple['predictions']):
            prediction_rows.append({'protocol': 'expanding_window', 'season': label(year), 'game_id': a['game_id'], 'start': a['start'],
                                    'forecast_cutoff': a['forecast_cutoff'], 'home': a['home'], 'away': a['away'],
                                    'home_win': a['home_win'], 'eligible_for_evaluation': a['eligible_for_evaluation'],
                                    'full_probability': a['home_probability'], 'simple_probability': b['home_probability']})
        write_json(args.output / 'results.json', output)
        print(json.dumps({'season': label(year), 'full': full['metrics']['log_loss'],
                          'simple': simple['metrics']['log_loss'], 'delta': comparison['differences']['log_loss']}), flush=True)
    # Direct comparison of the original three-season fit on both later seasons.
    # Reuse the same three-season simple-Elo fit already frozen in fold 2025.
    fixed_simple = Parameters(**json.loads((args.output / 'fit_2025.json').read_text())['simple_elo']['parameters'])
    fixed_full = Parameters(**release['parameters'])
    output['frozen_release_comparison'] = []
    for year in [2025, 2026]:
        full = replay(seasons[year], fixed_full, fitted=True, warmup_games=10)
        simple = replay(seasons[year], fixed_simple, fitted=True, warmup_games=10)
        output['frozen_release_comparison'].append({
            'training_seasons': [label(y) for y in [2022, 2023, 2024]],
            'evaluation_season': label(year), 'full_metrics': full['metrics'],
            'simple_metrics': simple['metrics'],
            'paired_comparison': paired_comparison(full['predictions'], simple['predictions'], seed=args.seed),
        })
        for a, b in zip(full['predictions'], simple['predictions']):
            prediction_rows.append({'protocol': 'original_frozen_release', 'season': label(year),
                                    'game_id': a['game_id'], 'start': a['start'],
                                    'forecast_cutoff': a['forecast_cutoff'], 'home': a['home'], 'away': a['away'],
                                    'home_win': a['home_win'], 'eligible_for_evaluation': a['eligible_for_evaluation'],
                                    'full_probability': a['home_probability'], 'simple_probability': b['home_probability']})
    write_json(args.output / 'results.json', output)
    with (args.output / 'predictions.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(prediction_rows[0]))
        writer.writeheader(); writer.writerows(prediction_rows)
    print('Comparison complete; production configuration and forecasts unchanged.', flush=True)


if __name__ == '__main__':
    main()
