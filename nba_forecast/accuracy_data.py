"""Read-only, source-separated evaluation of the dashboard's stored forecasts."""
import json
import math
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from .evaluation import favorite_bands
from .forecasting import Forecaster
from .live import digest
from .model import timestamp
from .reliability import team_calibration_evidence
from .replay import metrics
from .seasons import load_season


SOURCES = {
    'replay': 'Latest model · reconstructed history',
    'chronological': 'Earlier fits · chronological benchmark',
    'issued': 'Original issued track record',
}


def current_view_matches(archive, candidate, fingerprint, index=None):
    """Shared freshness contract for Games, ranks and the Accuracy dataset."""
    result = candidate.get('result', {})
    if (result.get('forecast_model_sha256') != fingerprint
            or candidate.get('source_result_sha256') != digest(archive['result'])):
        return False
    if index is not None:
        item = index.get('seasons', {}).get(archive['season'], {})
        if (index.get('forecast_model_sha256') != fingerprint
                or item.get('result_sha256') != digest(result)
                or item.get('input_sha256') != candidate.get('input_sha256')
                or item.get('source_result_sha256') != candidate.get('source_result_sha256')):
            return False
    return True


def verified_rows(rows, games, season, source, role=None):
    """Reject disagreements; never silently intersect a forecast and result set."""
    actual = {g['game_id']: g for g in games}
    if len(actual) != len(games):
        raise ValueError(f'{season}: duplicate source game IDs')
    output = []; seen = set()
    for row in rows:
        identifier = row['game_id']
        if identifier in seen:
            raise ValueError(f'{season}: duplicate forecast {identifier}')
        seen.add(identifier)
        game = actual.get(identifier)
        if game is None:
            raise ValueError(f'{season}: forecast {identifier} has no stored result')
        if (row['home'] != game['home']['name'] or row['away'] != game['away']['name']
                or row['home_win'] != int(game['home']['points'] > game['away']['points'])):
            raise ValueError(f'{season}: teams or outcome differ for {identifier}')
        for side in ['home', 'away']:
            if side+'_id' in row and row[side+'_id'] != game[side]['id']:
                raise ValueError(f'{season}: team ID differs for {identifier}')
            if side+'_score' in row and row[side+'_score'] != game[side]['points']:
                raise ValueError(f'{season}: score differs for {identifier}')
        p, q = row.get('home_probability'), row.get('away_probability')
        if not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in [p, q]) or abs(p+q-1) > 1e-12:
            raise ValueError(f'{season}: invalid probability for {identifier}')
        cutoff = row.get('issued_at') if source == 'issued' else row.get('forecast_cutoff')
        if not cutoff or timestamp(cutoff) >= min(timestamp(row['start']), timestamp(game['start'])):
            raise ValueError(f'{season}: missing or non-pregame cutoff for {identifier}')
        completion = game['last_play_at']
        if timestamp(completion) < timestamp(row['start']):
            raise ValueError(f'{season}: invalid completion for {identifier}')
        # Keep only fields needed for evaluation; do not copy mutable player state.
        output.append({k: row[k] for k in ['game_id', 'start', 'home', 'away', 'home_win',
                                          'home_probability', 'away_probability']} | {
            'season': season, 'source': source, 'evaluation_role': role,
            'kind': 'chronological_backtest' if source == 'chronological' else row.get('kind'),
            'forecast_cutoff': cutoff, 'last_play_at': completion,
            'source_start': game['start'],
            'schedule_changed': timestamp(row['start']) != timestamp(game['start']),
            'forecast_model_sha256': row.get('forecast_model_sha256'),
            'model_version': row.get('model_version'),
        })
    return output


def accuracy_catalog(root, entries, selected_archive=None, validate_index=True, archives=None):
    """Use the same snapshot/bundle checks as Games; fail closed on bad evidence."""
    root = Path(root); archives = Path(archives) if archives is not None else root/'data/seasons'
    catalog = {name: [] for name in SOURCES}; notices = []
    raw_by_season = {}; season_by_id = {}; inventory = {}
    fingerprint = Forecaster(json.loads((root/'models/nba-v0.3/bundle.json').read_text())).fingerprint
    for entry in entries:
        season = entry['season']
        archive = selected_archive if selected_archive and selected_archive['season'] == season else load_season(archives, entry)
        if not archive or 'result' not in archive:
            continue
        games = archive.get('_internal', {}).get('games')
        path = archives/season/'games.json'
        if games is None:
            games = json.loads(path.read_text()) if path.exists() else []
        raw_by_season[season] = games
        for game in games:
            if game['game_id'] in season_by_id:
                raise ValueError('Duplicate game ID across season archives')
            season_by_id[game['game_id']] = season
        original = archive['result']['predictions']
        issued = [r for r in original if r.get('kind') == 'issued_live' and r.get('home_probability') is not None]
        catalog['issued'].extend(verified_rows(issued, games, season, 'issued'))
        if archive.get('status') == 'live':
            missing = len(original)-len(issued)
            if missing:
                notices.append(f'{season}: {missing} completed games have no original issued probability and are excluded from issued scores.')
        replay_path = archives/season/'current-model.json'
        if replay_path.exists():
            candidate = json.loads(replay_path.read_text()); result = candidate['result']
            if result.get('forecast_model_sha256') == fingerprint and candidate.get('source_result_sha256') == digest(archive['result']):
                if {r['game_id'] for r in result['predictions']} != {r['game_id'] for r in original}:
                    raise ValueError(f'{season}: current replay game set differs from the stored completed forecasts')
                if any(r.get('forecast_model_sha256') != fingerprint or r.get('model_version') != result['model_version'] for r in result['predictions']):
                    raise ValueError(f'{season}: mixed model versions in latest-model history')
                catalog['replay'].extend(verified_rows(result['predictions'], games, season, 'replay', result.get('evaluation_role')))
                inventory[season] = {'file': f'{season}/current-model.json', 'source_result_sha256': candidate['source_result_sha256'],
                                     'input_sha256': candidate.get('input_sha256'), 'result_sha256': digest(result),
                                     'games': len(result['predictions']), 'evaluation_role': result.get('evaluation_role')}
            else:
                notices.append(f'{season}: current-method replay is stale and excluded, matching the Games fallback policy.')
    audit_path = root/'models/nba-v0.3/matched-evaluation.json'
    if audit_path.exists():
        groups = defaultdict(list)
        audit = json.loads(audit_path.read_text())
        if {r['game_id'] for r in audit['published_rows']} != set(audit['pooled']['game_ids']):
            raise ValueError('Chronological benchmark game set differs from its matched-sample audit')
        for row in audit['published_rows']:
            if row['game_id'] not in season_by_id:
                raise ValueError('Chronological forecast has no stored season/result')
            groups[season_by_id[row['game_id']]].append(row)
        for season, rows in groups.items():
            catalog['chronological'].extend(verified_rows(rows, raw_by_season[season], season, 'chronological'))
    index_path = archives/'current-model-index.json'
    if validate_index and index_path.exists():
        index = json.loads(index_path.read_text())
        if index.get('forecast_model_sha256') != fingerprint or index.get('seasons') != inventory:
            catalog['replay'] = []
            notices.append('The latest-model dataset is being rebuilt: its version index does not match the model and season files. Latest-model analysis is withheld; archived records remain separate.')
    for source, rows in catalog.items():
        changed = sum(r['schedule_changed'] for r in rows)
        if changed:
            notices.append(f'{SOURCES[source]}: {changed} forecasts retain a scheduled start that differs from the completed-game source. Both times are exported; cutoffs precede both.')
    return catalog, notices


def write_current_index(root, archives):
    """Publish one version-bound inventory and persisted summaries after replay."""
    from .data import write_json
    root = Path(root); archives = Path(archives)
    entries = json.loads((archives/'index.json').read_text())['seasons']
    catalog, notices = accuracy_catalog(root, entries, validate_index=False, archives=archives)
    forecaster = Forecaster(json.loads((root/'models/nba-v0.3/bundle.json').read_text()))
    inventory = {}
    for season in sorted({r['season'] for r in catalog['replay']}):
        saved = json.loads((archives/season/'current-model.json').read_text()); result = saved['result']
        inventory[season] = {'file': f'{season}/current-model.json', 'source_result_sha256': saved['source_result_sha256'],
                             'input_sha256': saved.get('input_sha256'), 'result_sha256': digest(result),
                             'games': len(result['predictions']), 'evaluation_role': result.get('evaluation_role')}
    expected = {e['season'] for e in entries if e.get('file') and 'result' in json.loads((archives/e['file']).read_text())}
    if set(inventory) != expected:
        raise ValueError('Latest-model replay inventory does not cover every completed season')
    rows = catalog['replay']; teams = sorted({r[s] for r in rows for s in ['home', 'away']})
    payload = {'schema_version': 1, 'model_version': forecaster.bundle['version'],
               'forecast_model_sha256': forecaster.fingerprint, 'seasons': inventory,
               'summary': metrics(rows), 'season_summary': season_scores(rows),
               'team_season_summary': [{'Season': season, **r} for season in inventory
                                       for r in team_scores([g for g in rows if g['season'] == season])],
               'team_probability_bands': {team: team_bands(rows, team, allow_replay=True) for team in teams},
               'interpretation': 'Descriptive latest-model reconstruction. Training seasons measure historical fit, not unseen-game accuracy.',
               'source_notes': notices}
    write_json(archives/'current-model-index.json', payload)
    return payload


def _summary(rows):
    m = metrics(rows)
    return {'Games': m['games'], 'Winner accuracy': m['winner_accuracy'],
            'Brier score': m['brier_score'], 'Log loss': m['log_loss']}


def evidence_before(rows, forecast, source):
    """Match Games' pregame evidence window and same-bundle issued policy."""
    cutoff = forecast.get('issued_at') or forecast.get('forecast_cutoff')
    if not cutoff:
        raise ValueError('Reference forecast has no pregame cutoff')
    return [r for r in rows if timestamp(r['last_play_at']) < timestamp(cutoff)
            and (source != 'issued' or (forecast.get('forecast_model_sha256')
                 and r.get('forecast_model_sha256') == forecast['forecast_model_sha256']))]


def season_scores(rows):
    return [{'Season': season, **_summary([r for r in rows if r['season'] == season]),
             'Evaluation role': ', '.join(sorted({{'training_replay': 'Historical fit (training)',
                 'post_fit_replay': 'Post-fit reconstruction'}.get(r.get('evaluation_role'), SOURCES[r['source']])
                 for r in rows if r['season'] == season}))}
            for season in sorted({r['season'] for r in rows}, reverse=True)]


def team_scores(rows):
    output = []
    for team in sorted({r[s] for r in rows for s in ['home', 'away']}):
        games = [r for r in rows if team in [r['home'], r['away']]]
        expected = sum(r['home_probability'] if r['home'] == team else r['away_probability'] for r in games)
        wins = sum(r['home_win'] if r['home'] == team else 1-r['home_win'] for r in games)
        output.append({'Team': team, **_summary(games), 'Expected wins': expected, 'Actual wins': wins,
                       'Wins − expected': wins-expected, 'Mean forecast': expected/len(games),
                       'Actual win rate': wins/len(games), 'Calibration gap (pp)': (wins-expected)/len(games)*100})
    return output


def team_bands(rows, team, before=None, exact_model=False, fingerprint=None, allow_replay=False):
    """Reuse Games' exact ten-point binning, Wilson intervals and sample labels."""
    if not rows:
        return []
    before = before or (max(timestamp(r['last_play_at']) for r in rows)+timedelta(microseconds=1)).isoformat()
    output = []
    for index in range(10):
        p = (index+.5)/10
        target = {'home': team, 'away': '__other__', 'home_probability': p, 'away_probability': 1-p,
                  'forecast_model_sha256': fingerprint}
        item = team_calibration_evidence(target, rows, team, before, exact_model=exact_model, allow_replay=allow_replay)
        output.append({'Probability range': item['band'], 'Games': item['games'],
                       'Wins': item['wins'],
                       'Mean forecast': item['mean_forecast'], 'Actual win rate': item['observed_win_rate'],
                       'Winner accuracy': item['winner_accuracy'],
                       'Calibration gap (pp)': item['raw_error_pp'],
                       'Observed-rate 95% interval': item['observed_rate_interval_95'], 'Evidence': item['sample_label']})
    return output


def favorite_calibration(rows):
    return [{'Probability range': r['band'], 'Games': r['games'], 'Wins': r['wins'],
             'Mean forecast': r['mean_forecast'], 'Actual win rate': r['observed_win_rate'],
             'Calibration gap (pp)': (r['observed_win_rate']-r['mean_forecast'])*100,
             'Winner accuracy': r['observed_win_rate'],
             'Lower 95%': r['lower_95'], 'Upper 95%': r['upper_95']} for r in favorite_bands(rows)]
