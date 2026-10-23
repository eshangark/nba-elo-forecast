"""Current-method reconstructions, separate from immutable issued forecasts."""

import gzip
import json
from itertools import groupby
from pathlib import Path

from .data import write_json
from .forecasting import FeatureState, Forecaster, carryover_ratings, log_odds, ridge_probability
from .live import digest
from .model import Engine, Parameters, slate_date, timestamp
from .replay import metrics, replay, slate_cutoff

POLICY_VERSION = 'current-method-v1'


def current_result(rows, rankings, forecaster, season):
    training = season in forecaster.bundle.get('training_seasons', [])
    # Bundles may list ending years rather than season labels.
    training = training or int(season[:4])+1 in forecaster.bundle.get('training_season_end_years', [])
    return {'status': 'current_method_replay', 'model_version': forecaster.bundle['version'],
            'forecast_model_sha256': forecaster.fingerprint, 'parameters': forecaster.bundle['core_parameters'],
            'evaluation_role': 'training_replay' if training else 'post_fit_replay',
            'metrics': metrics([r for r in rows if r['eligible_for_evaluation']]),
            'metrics_all_issued': metrics(rows), 'warmup_games': 10,
            'rankings': rankings, 'predictions': rows, 'replay_policy': POLICY_VERSION}


def corrected_prediction(game, base, state, context, forecaster):
    """Use captured raw reports, or the saved pregame injury covariates if older."""
    cutoff = timestamp(context['cutoff'])
    if cutoff >= timestamp(game['start']):
        raise ValueError('Reconstruction cutoff must precede tip-off')
    source = context.get('source')
    if source and (timestamp(source['published_at']) > cutoff or
                   (cutoff-timestamp(source['published_at'])).total_seconds() > 16*3600):
        raise ValueError('Reconstruction injury source is future-dated or stale')
    if context.get('report') is not None:
        adjustment = forecaster.predict(game, base, state, context['report'], source)
        basis = 'captured_report_and_prior_player_history'
    elif context.get('injury_features') is not None and source:
        # Old issued rows contain raw (not standardized) injury inputs. Recompute
        # their base log odds and apply the CURRENT head's scaler/coefficients.
        inputs = [log_odds(base['home_probability'])]+context['injury_features'][1:]
        probability = ridge_probability(forecaster.bundle['injury_head'], inputs, base['home_probability'])
        adjustment = {'home_probability': probability, 'away_probability': 1-probability,
                      'injury_source': source, 'injury_status': 'saved_pregame_features'}
        basis = 'saved_pregame_injury_covariates'
    else:
        adjustment = {'home_probability': base['home_probability'], 'away_probability': base['away_probability'],
                      'injury_source': None, 'injury_status': 'elo_fallback'}
        basis = 'no_recoverable_pregame_injury_inputs'
    row = {**base, **adjustment, 'kind': 'current_method_replay',
           'forecast_cutoff': context['cutoff'], 'replay_input_basis': basis,
           'forecast_model_sha256': forecaster.fingerprint, 'model_version': forecaster.bundle['version']}
    row.pop('probability_models', None)
    row.pop('forecast_features', None)
    return row


def live_contexts(snapshot):
    """Recover the last actual pregame information set, never a later report."""
    internal = snapshot['_internal']
    contexts = {}
    for game in internal['games']:
        candidates = [r for r in internal['forecasts'] if r['game_id'] == game['game_id']
                      and r.get('home_id') == game['home']['id'] and r.get('away_id') == game['away']['id']
                      and timestamp(r['issued_at']) < timestamp(game['start'])]
        if candidates:
            issued = max(candidates, key=lambda r: timestamp(r['issued_at']))
            context = {'cutoff': issued['issued_at'], 'source': issued.get('injury_source'),
                       'report': issued.get('injury_report'),
                       'injury_features': (issued.get('forecast_features') or {}).get('injury'),
                       'home_context': issued['home_context'], 'away_context': issued['away_context']}
        else:
            day = slate_date(game)
            batch = [g for g in internal['games'] if slate_date(g) == day]
            context = {'cutoff': slate_cutoff(day, batch).isoformat(), 'source': None}
        contexts[game['game_id']] = context
    return contexts


def replay_live(snapshot, forecaster):
    """Replay rating/player histories at their recorded completion times."""
    internal = snapshot['_internal']
    games, roster = internal['games'], internal['roster']
    initial = internal['initialization']
    state = FeatureState(initial['feature_seed'])
    engine = Engine(Parameters(**forecaster.bundle['core_parameters']))
    for team in roster:
        engine.team(team).rating = initial['ratings'][team]
    contexts = live_contexts(snapshot)
    events, rows, update_rows = [], {}, {}
    for game in games:
        events.extend([(timestamp(contexts[game['game_id']]['cutoff']), 1, game['game_id'], game),
                       (timestamp(game['start']), 2, game['game_id'], game),
                       (timestamp(game['last_play_at']), 0, game['game_id'], game)])
    for _, kind, identifier, game in sorted(events, key=lambda e: e[:3]):
        if kind == 1:
            context = contexts[identifier]
            base = engine.predict(game, contexts=context if 'home_context' in context else None)
            rows[identifier] = corrected_prediction(game, base, state, context, forecaster)
            rows[identifier]['eligible_for_evaluation'] = all(engine.team(game[s]['id']).games >= 10 for s in ['home','away'])
        elif kind == 2:
            update_rows[identifier] = engine.predict(game)
        else:
            base = update_rows[identifier]
            engine.update(game, base)
            engine.recenter()
            state.observe(game, base['home_probability'], internal.get('player_games', {}).get(identifier))
            rows[identifier].update(home_win=int(game['home']['points'] > game['away']['points']),
                                    home_score=game['home']['points'], away_score=game['away']['points'],
                                    home_rating_after=engine.team(game['home']['id']).rating,
                                    away_rating_after=engine.team(game['away']['id']).rating)
    rankings = sorted([{'team_id': t, 'team': roster[t], 'elo': team.rating, 'games': team.games, 'wins': team.wins}
                       for t, team in engine.teams.items()], key=lambda r: (-r['elo'],r['team']))
    ordered = [rows[g['game_id']] for g in sorted(games,key=lambda g:(timestamp(g['start']),g['game_id']))]
    return current_result(ordered, rankings, forecaster, snapshot['season'])


def refresh_current_replays(root, archives=None):
    """Regenerate all seasons with one current method, without rewriting archives."""
    root = Path(root)
    forecaster = Forecaster(json.loads((root/'models/nba-v0.3/bundle.json').read_text()))
    archives = Path(archives) if archives is not None else root/'data/seasons'
    previous_ratings, state = {}, FeatureState()
    index = json.loads((archives/'index.json').read_text())
    entries = {row['season']:row for row in index['seasons']}
    for directory in sorted(archives.iterdir()):
        if not directory.is_dir():
            continue
        season = directory.name
        if (directory/'live.json').exists():
            snapshot = json.loads((directory/'live.json').read_text())
            if snapshot['_internal'].get('forecast_model_sha256') != forecaster.fingerprint:
                continue  # Collector must first rebuild this season with the new bundle.
            result = replay_live(snapshot, forecaster)
            inputs_hash = digest({'games':snapshot['_internal']['games'], 'contexts':live_contexts(snapshot),
                                  'players':snapshot['_internal'].get('player_games'), 'initialization':snapshot['_internal']['initialization']})
        elif (directory/'replay-inputs.json.gz').exists():
            games = json.loads((directory/'games.json').read_text())
            inputs = json.loads(gzip.decompress((directory/'replay-inputs.json.gz').read_bytes()))
            roster = {g[s]['id']:g[s]['name'] for g in games for s in ['home','away']}
            initial = carryover_ratings(previous_ratings, roster, forecaster.bundle['carryover_fraction'])
            state.start_season(season)
            base_result = replay(games, Parameters(**forecaster.bundle['core_parameters']), fitted=True,
                                 warmup_games=10, initial_ratings=initial)
            base_rows = {r['game_id']:r for r in base_result['predictions']}
            rows = []
            for day, batch in groupby(sorted(games,key=lambda g:(timestamp(g['start']),g['game_id'])),slate_date):
                batch = list(batch)
                for game in batch:
                    base = base_rows[game['game_id']]
                    rows.append(corrected_prediction(game,base,state,inputs['contexts'][game['game_id']],forecaster))
                for game in batch:
                    state.observe(game,base_rows[game['game_id']]['home_probability'],inputs['players'].get(game['game_id']))
            previous_ratings = {r['team_id']:r['elo'] for r in base_result['rankings']}
            result = current_result(rows,base_result['rankings'],forecaster,season)
            inputs_hash = digest({'games':games,'inputs':inputs})
        else:
            continue
        source = json.loads((archives/entries[season]['file']).read_text())
        write_json(directory/'current-model.json', {'season':season,'result':result,'input_sha256':inputs_hash,
                   'source_result_sha256':digest(source['result']),
                   'provenance':'Current-method retrospective reconstruction; original issued forecasts and chronological backtests remain separate.'})
