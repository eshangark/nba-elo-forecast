"""Prepare causal histories, backtest both heads, and freeze a future-season bundle."""

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nba_forecast.data import write_json
from nba_forecast.forecasting import FeatureState, Forecaster, carryover_ratings
from nba_forecast.model import Parameters
from nba_forecast.fitting import fit
from nba_forecast.replay import metrics
from nba_forecast.evaluation import compare_variants
from nba_forecast.training import (load_history, load_players, prepare_history, fit_heads, rating_path, make_bundle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--players', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('models/nba-v0.3'))
    parser.add_argument('--maxiter', type=int, default=150)
    parser.add_argument('--backtest', action='store_true')
    parser.add_argument('--prepared-output', type=Path, help='Optional diagnostic feature rows outside Git')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    seasons = load_history(root)
    players, aliases, audit = load_players(seasons, args.players)
    reports = json.loads(args.reports.read_text())
    print('Preparing prior-only histories', flush=True)
    rows, seeds, paths, state = prepare_history(root, seasons, players, aliases, reports)
    if args.prepared_output:
        write_json(args.prepared_output, {'rows': rows, 'feature_seeds': seeds})
    args.output.mkdir(parents=True, exist_ok=True)
    if args.backtest:
        scores = []
        for year in list(seasons)[2:]:
            print('Fitting retrospective fold', year, flush=True)
            injury, boosted, selection = fit_heads(rows, year)
            result = copy.deepcopy(paths[year])
            initial = {'season': f'{year-1}-{str(year)[-2:]}', 'ratings': result['initial_ratings'], 'features': seeds[year]}
            params = Parameters(**result['parameters'])
            bundle = make_bundle(params, injury, boosted, initial, aliases, [y for y in seasons if y < year], selection)
            predictor = Forecaster(bundle)
            fold_state = FeatureState(seeds[year])
            lookup = {r['game_id']: r for r in rows if r['year'] == year}
            base_rows = {r['game_id']: r for r in result['predictions']}
            for g in seasons[year]:
                r = lookup[g['game_id']]
                base = base_rows[g['game_id']]
                base.update(predictor.predict(g, base, fold_state, r['report'], r['source']))
                fold_state.observe(g, r['base'], players.get(g['game_id']))
            matched_all = compare_variants(result["predictions"])
            matched_established = compare_variants(result["predictions"], established=True)
            comparisons = {}
            for variant in ['base', 'injury', 'boosted']:
                comparisons[variant] = {'metrics': matched_established['metrics'][variant],
                                        'metrics_all_issued': matched_all['metrics'][variant]}
            result.update(model_version='0.3.0', status='retrospective_historical_replay',
                          evaluation_role='retrospective', metrics=comparisons['injury']['metrics'],
                          metrics_all_issued=comparisons['injury']['metrics_all_issued'], model_comparison=comparisons,
                          probability_selection=bundle['selection'], matched_sample_sha256=matched_all['sample_sha256'])
            original = json.loads((root/f'data/seasons/{initial["season"]}/snapshot.json').read_text())
            archive = {'season': initial['season'], 'status': 'complete_historical_replay',
                       'coverage': original['coverage'], 'result': result,
                       'provenance': 'Retrospective nested selection; unavailable-report fallback is included.'}
            write_json(args.output/f'folds/{year}.json', bundle)
            write_json(args.output/f'folds/{year}-selection.json', selection)
            write_json(root/f'data/seasons/{initial["season"]}/snapshot-v0.3.json', archive)
            scores.append({'season': initial['season'], 'model_comparison': comparisons})
        from scripts.audit_comparisons import audit
        audit(root)
        pooled = {}
        for variant in ['base', 'injury', 'boosted']:
            values = [row['model_comparison'][variant]['metrics_all_issued'] for row in scores]
            count = sum(row['games'] for row in values)
            pooled[variant] = {'games': count, **{key: sum(row[key]*row['games'] for row in values)/count
                                                 for key in ['log_loss', 'brier_score', 'winner_accuracy']}}
        write_json(args.output/'evaluation.json', {'protocol': 'Earlier fit seasons; last prior season selects; next season evaluates. Retrospective.',
                                                 'pooled_all_games': pooled,
                                                 'folds': scores, 'primary': 'injury', 'challenger': 'boosted',
                                                 'limitations': ['Previously observed historical outcomes', 'Model-family selection is exploratory',
                                                                 'Morning reports may be unsubmitted; missing game coverage uses Elo fallback']})
    target = max(seasons)+1
    print('Fitting future-season release', target, flush=True)
    params, report = fit(list(seasons.values()), seed=42, maxiter=args.maxiter)
    write_json(args.output/'core-fit.json', report)
    injury, boosted, selection = fit_heads(rows, target)
    final_path = rating_path(seasons, params)[max(seasons)]
    roster = {t['team_id']: t['team'] for t in final_path['rankings']}
    previous = {t['team_id']: t['elo'] for t in final_path['rankings']}
    season = f'{target-1}-{str(target)[-2:]}'
    state.start_season(season)
    initial = {'season': season, 'ratings': carryover_ratings(previous, roster), 'features': state.data}
    bundle = make_bundle(params, injury, boosted, initial, aliases, list(seasons), selection)
    write_json(args.output/'bundle.json', bundle)
    write_json(args.output/'selection.json', selection)
    write_json(args.output/'data-quality.json', {'player_archives': audit,
                                              'canonical_sha256': {str(year): hashlib.sha256(json.dumps(games, sort_keys=True).encode()).hexdigest() for year, games in seasons.items()},
                                              'normalized_reports_sha256': hashlib.sha256(args.reports.read_bytes()).hexdigest(),
                                              'report_dates': len(reports), 'training_games': len(rows)})
    print('Frozen', season, 'with both probability heads', flush=True)


if __name__ == '__main__':
    main()
