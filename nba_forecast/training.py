"""Offline preparation and chronological fitting for versioned probability heads.

Scientific dependencies are imported here, never by the dashboard or live scorer.
"""

import copy
import hashlib
import itertools
import json
import math
from dataclasses import asdict
from itertools import groupby
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit
from sklearn.ensemble import HistGradientBoostingClassifier

from .forecasting import FeatureState, INJURY_FEATURES, TEAM_FEATURES, carryover_ratings, tree_probability
from .injuries import player_key, join_report
from .model import Parameters, slate_date, timestamp
from .players import validated_players
from .replay import replay, slate_cutoff

PENALTIES = [.0001, .001, .01, .1, 1., 10.]


def probability_loss(p, y):
    p = np.clip(p, 1e-12, 1-1e-12)
    return float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p)))


def load_history(root):
    seasons = {}
    index = json.loads((Path(root)/'data/seasons/index.json').read_text())
    complete = {entry['season'] for entry in index['seasons'] if entry['status'] == 'complete_historical_replay'}
    for path in sorted((Path(root)/'data/seasons').glob('*/games.json')):
        games = sorted(json.loads(path.read_text()), key=lambda g: (timestamp(g['start']), g['game_id']))
        if path.parent.name in complete and len(games) != 1230:
            raise ValueError('A complete historical archive lost games')
        if len(games) == 1230:
            counts = Counter(g[s]['id'] for g in games for s in ['home', 'away'])
            if len(counts) != 30 or set(counts.values()) != {82} or len({g['season'] for g in games}) != 1:
                raise ValueError('Incomplete season/team coverage')
            seasons[games[0]['season']] = games
    if not seasons:
        raise ValueError('No complete historical seasons')
    return seasons


def rating_path(seasons, params, fraction=.5):
    previous, results = {}, {}
    for year, games in sorted(seasons.items()):
        roster = {g[s]['id']: g[s]['name'] for g in games for s in ['home', 'away']}
        initial = carryover_ratings(previous, roster, fraction)
        result = replay(games, params, fitted=True, warmup_games=10, initial_ratings=initial)
        result['initial_ratings'] = initial
        previous = {r['team_id']: r['elo'] for r in result['rankings']}
        results[year] = result
    return results


def load_players(seasons, folder):
    lookup, aliases, audit = {}, {}, []
    fields = {'points': 'points', 'field_goals_made': 'fgm', 'field_goals_attempted': 'fga',
              'three_point_field_goals_made': 'threem', 'three_point_field_goals_attempted': 'threea',
              'free_throws_made': 'ftm', 'free_throws_attempted': 'fta', 'offensive_rebounds': 'oreb',
              'defensive_rebounds': 'dreb', 'assists': 'ast', 'steals': 'stl', 'turnovers': 'tov',
              'blocks': 'blk', 'fouls': 'pf'}
    for year, games in seasons.items():
        path = Path(folder)/f'player_box_{year}.parquet'
        frame = pd.read_parquet(path)
        for athlete, name in frame[['athlete_id', 'athlete_display_name']].dropna().drop_duplicates().itertuples(index=False, name=None):
            aliases.setdefault(player_key(name), set()).add(str(int(athlete)))
        ids = {g['game_id'] for g in games}
        frame = frame[frame.game_id.astype(str).isin(ids)]
        if frame.duplicated(['game_id', 'team_id', 'athlete_id']).any():
            raise ValueError('Duplicate source player identity')
        groups = {(str(game), str(team)): rows for (game, team), rows in frame.groupby(['game_id', 'team_id'])}
        failures, passed = [], 0
        for g in games:
            value = {}
            for side in ['home', 'away']:
                team = g[side]['id']
                try:
                    source = groups[(g['game_id'], team)]
                    if set(source['opponent_team_id'].astype(str)) != {g['away' if side == 'home' else 'home']['id']}:
                        raise ValueError('Player opponent identity mismatch')
                    rows = []
                    for r in source[source.minutes.fillna(0) > 0].itertuples():
                        row = {target: float(getattr(r, field)) for field, target in fields.items()}
                        row.update(athlete=str(int(r.athlete_id)), minutes=float(r.minutes))
                        rows.append(row)
                    value[team] = validated_players(rows, g[side])
                    passed += 1
                except (KeyError, ValueError, OverflowError) as exc:
                    value[team] = None
                    failures.append({'game_id': g['game_id'], 'team_id': team, 'error': str(exc)})
            lookup[g['game_id']] = value
        audit.append({'season_end_year': year, 'validated_team_games': passed, 'failures': failures,
                      'url': f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_boxscores/{path.name}',
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return lookup, {name: sorted(ids) for name, ids in aliases.items()}, audit


def prepare_history(root, seasons, players, aliases, reports):
    """Historical training covariates use that year's earlier-prefix core fit."""
    state = FeatureState()
    rows, seeds, replays = [], {}, {}
    for year, games in sorted(seasons.items()):
        prefix = {y: g for y, g in seasons.items() if y <= year}
        fit_path = Path(root)/f'models/comparison-v0.2/fit_{year}.json'
        if year == min(seasons):
            params = Parameters()
        elif fit_path.exists():
            fitted = json.loads(fit_path.read_text())
            expected = [f'{y-1}-{str(y)[-2:]}' for y in seasons if y < year]
            if fitted['training_seasons'] != expected:
                raise ValueError('Historical base covariates require an earlier-prefix-only fit')
            params = Parameters(**fitted['full_model']['parameters'])
        else:
            from .fitting import fit
            params, _ = fit([games for y, games in seasons.items() if y < year], seed=42, maxiter=150)
        result = rating_path(prefix, params)[year]
        replays[year] = result
        season = f'{year-1}-{str(year)[-2:]}'
        state.start_season(season)
        seeds[year] = copy.deepcopy(state.data)
        predictions = {r['game_id']: r for r in result['predictions']}
        for day, batch in groupby(games, slate_date):
            batch = list(batch)
            cutoff = slate_cutoff(day, batch)
            report = reports.get(str(day))
            mapped = join_report(report, batch, aliases, cutoff) if report else {}
            for g in batch:
                base = predictions[g['game_id']]
                injury, coverage = state.injury_features(g, mapped.get(g['game_id'], {}))
                rows.append({'year': year, 'game_id': g['game_id'], 'base': base['home_probability'],
                             'injury': injury, 'team': state.team_features(g, base),
                             'coverage': coverage, 'report': mapped.get(g['game_id'], {}),
                             'source': {k: report[k] for k in ['published_at', 'sha256']} if report else None,
                             'outcome': int(g['home']['points'] > g['away']['points']), 'cutoff': cutoff.isoformat()})
            for g in batch:
                state.observe(g, predictions[g['game_id']]['home_probability'], players.get(g['game_id']))
    return rows, seeds, replays, state


def fit_ridge(X, z, y, mask, penalty):
    means, scales = X[mask].mean(axis=0), X[mask].std(axis=0)
    scales[scales < 1e-10] = 1
    A = np.column_stack([np.ones(len(X)), (X-means)/scales])
    train, target, offset = A[mask], y[mask], z[mask]
    def objective(w):
        linear = offset+train@w
        return (np.mean(np.logaddexp(0, linear)-target*linear)+penalty*.5*np.sum(w*w),
                train.T@(expit(linear)-target)/len(target)+penalty*w)
    result = minimize(objective, np.zeros(A.shape[1]), jac=True, method='L-BFGS-B',
                      options={'maxiter': 500, 'ftol': 1e-11, 'gtol': 1e-7})
    if not result.success:
        raise ValueError('Probability-head fit failed: '+str(result.message))
    model = {'means': means.tolist(), 'scales': scales.tolist(), 'weights': result.x.tolist(),
             'penalty': penalty, 'converged': bool(result.success)}
    return expit(z+A@result.x), model


def export_trees(model, blend):
    trees = []
    for predictors in model._predictors:
        if len(predictors) != 1:
            raise ValueError('Only binary numerical trees can be exported')
        nodes = []
        for row in predictors[0].nodes:
            if row['is_categorical']:
                raise ValueError('Categorical tree is not supported')
            nodes.append({'leaf': bool(row['is_leaf']), 'value': float(row['value']),
                          'feature': int(row['feature_idx']), 'threshold': float(row['num_threshold']),
                          'left': int(row['left']), 'right': int(row['right'])})
        trees.append(nodes)
    return {'intercept': float(model._baseline_prediction[0, 0]), 'blend': blend, 'trees': trees}


def fit_heads(rows, target_year):
    if len({r['game_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate game IDs in fitting/validation sample')
    years = np.array([r['year'] for r in rows])
    base = np.array([r['base'] for r in rows]); z = logit(base); y = np.array([r['outcome'] for r in rows])
    Xi = np.column_stack([z, np.array([r['injury'] for r in rows])])
    Xb = np.column_stack([z, np.array([r['team'] for r in rows]), np.array([r['injury'] for r in rows])])
    train, validation, all_prior = years < target_year-1, years == target_year-1, years < target_year
    if not train.any() or not validation.any():
        raise ValueError('Nested selection requires at least two earlier seasons')
    ridge_search = [{'penalty': None, 'validation_log_loss': probability_loss(base[validation], y[validation])}]
    for penalty in PENALTIES:
        p, _ = fit_ridge(Xi, z, y, train, penalty)
        ridge_search.append({'penalty': penalty, 'validation_log_loss': probability_loss(p[validation], y[validation])})
    chosen = min(ridge_search, key=lambda r: r['validation_log_loss'])
    injury = fit_ridge(Xi, z, y, all_prior, chosen['penalty'])[1] if chosen['penalty'] is not None else {'unchanged_base': True}
    booster_search = [{'config': None, 'blend': 0., 'validation_log_loss': probability_loss(base[validation], y[validation]),
                       'validation_accuracy': float(np.mean((base[validation] >= .5) == y[validation]))}]
    def estimator(config):
        return HistGradientBoostingClassifier(**config, loss='log_loss', random_state=42, early_stopping=False,
                                              min_samples_leaf=50, max_bins=255, max_leaf_nodes=15)
    for depth, rate, iterations, penalty in itertools.product([2, 3], [.03, .1], [100, 250], [1., 10.]):
        config = dict(max_depth=depth, learning_rate=rate, max_iter=iterations, l2_regularization=penalty)
        model = estimator(config).fit(Xb[train], y[train])
        prediction = model.predict_proba(Xb[validation])[:, 1]
        for weight in [.25, .5, .75, 1.]:
            p = (1-weight)*base[validation]+weight*prediction
            booster_search.append({'config': config, 'blend': weight,
                                   'validation_log_loss': probability_loss(p, y[validation]),
                                   'validation_accuracy': float(np.mean((p >= .5) == y[validation]))})
    selected = min(booster_search, key=lambda r: (-r['validation_accuracy'], r['validation_log_loss']))
    if selected['config'] is None:
        boosted = {'unchanged_base': True}
    else:
        model = estimator(selected['config']).fit(Xb[all_prior], y[all_prior])
        boosted = export_trees(model, selected['blend'])
        expected = (1-selected['blend'])*base+selected['blend']*model.predict_proba(Xb)[:, 1]
        portable = np.array([tree_probability(boosted, x, b) for x, b in zip(Xb, base)])
        if not np.allclose(expected, portable, rtol=0, atol=1e-12):
            raise AssertionError('Portable trees differ from the training estimator')
    validation_ids = sorted(r['game_id'] for r in rows if r['year'] == target_year-1)
    sample_hash = hashlib.sha256(json.dumps(validation_ids,separators=(',', ':')).encode()).hexdigest()
    return injury, boosted, {'validation_games': len(validation_ids), 'validation_game_ids': validation_ids,
                            'validation_sample_sha256': sample_hash,
                            'inner_validation_end_year': target_year-1, 'injury_selected': chosen,
                            'boosted_selected': selected, 'ridge_search': ridge_search, 'boosting_search': booster_search}


def make_bundle(params, injury, boosted, initialization, aliases, training_years, selection):
    return {'version': '0.3.0', 'feature_schema': {'injury': ['base_logit']+INJURY_FEATURES,
                                               'boosted': ['base_logit']+TEAM_FEATURES+INJURY_FEATURES},
            'core_parameters': asdict(params), 'carryover_fraction': .5, 'injury_head': injury,
            'boosted_head': boosted, 'initialization': initialization, 'player_aliases': aliases,
            'training_season_end_years': training_years,
            'selection': {k: v for k, v in selection.items() if not k.endswith('_search')},
            'policy': 'Base Elo updates ratings; injury is primary; boosted is a challenger. Unavailable report/game coverage falls back to base Elo.'}
