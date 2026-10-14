"""Atomic live snapshots with immutable, genuinely issued forecast revisions."""

import copy
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta

from .data import BASE
from .model import EASTERN, Engine, MODEL_VERSION, timestamp
from .replay import metrics
from .validation import validate_game


@contextmanager
def live_lock(archives):
    """Single writer on macOS/Linux; the OS releases the lock on process exit."""
    import fcntl
    root = Path(archives)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.live-update.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another live update is already running') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def event_kind(event, year):
    season = event['season']
    if int(season['year']) != year or int(season['type']) != 2:
        return 'excluded'
    competition = event['competitions'][0]
    category = competition.get('type', {}).get('abbreviation')
    if category in {'CC', 'ALLSTAR'}:
        return 'excluded'
    if category != 'STD':
        raise ValueError(f"Unknown regular-season category: {event['id']} / {category}")
    status = competition['status']['type']
    if status.get('name') in {'STATUS_CANCELED', 'STATUS_CANCELLED', 'STATUS_POSTPONED'}:
        return 'inactive'
    if status['completed']:
        return 'final'
    if status['state'] not in {'pre', 'in'}:
        raise ValueError(f"Unsupported event state: {event['id']}")
    return 'pending'


def parse_schedule(event, cities):
    competition = event['competitions'][0]
    teams = {c['homeAway']: c['team'] for c in competition['competitors']}
    if set(teams) != {'home', 'away'} or teams['home']['id'] == teams['away']['id']:
        raise ValueError('Invalid schedule opponents')
    venue = competition['venue']
    start = competition['date']
    timestamp(start)
    return {'game_id': str(event['id']), 'start': start, 'season': int(event['season']['year']),
            'season_type': 2, 'neutral': bool(competition.get('neutralSite', False)),
            'venue_id': str(venue['id']), 'venue_name': venue['fullName'],
            'location': cities.resolve(venue['address']),
            'home': {'id': str(teams['home']['id']), 'name': teams['home']['displayName']},
            'away': {'id': str(teams['away']['id']), 'name': teams['away']['displayName']},
            'event_state': competition['status']['type']['state'],
            'source': f"{BASE}/scoreboard?dates={timestamp(start).astimezone(EASTERN):%Y%m%d}"}


def rebuild(games, params, roster, now):
    """Reconstruct rating state; these estimates are never issued retrospectively."""
    engine = Engine(params)
    for identifier in roster:
        engine.team(identifier)
    if len({g['game_id'] for g in games}) != len(games):
        raise ValueError('Duplicate completed games')
    timeline = []
    for g in games:
        validate_game(g)
        if timestamp(g['last_play_at']) > now:
            raise ValueError('Completion proxy is in the future')
        if any(g[s]['id'] not in roster for s in ['home', 'away']):
            raise ValueError('Unknown team identity')
        timeline.extend([(timestamp(g['start']), 1, g['game_id'], g),
                         (timestamp(g['last_play_at']), 0, g['game_id'], g)])
    predictions, active = {}, set()
    for _, kind, _, g in sorted(timeline, key=lambda x: x[:3]):
        ids = {g[s]['id'] for s in ['home', 'away']}
        if kind == 1:
            if ids & active:
                raise ValueError('Overlapping games for one team')
            predictions[g['game_id']] = engine.predict(g)
            active.update(ids)
        else:
            row = predictions[g['game_id']]
            engine.update(g, row)
            engine.recenter()
            row.update(home_win=int(g['home']['points'] > g['away']['points']),
                       home_score=g['home']['points'], away_score=g['away']['points'],
                       home_rating_after=engine.team(g['home']['id']).rating,
                       away_rating_after=engine.team(g['away']['id']).rating)
            active.difference_update(ids)
    return engine, predictions


def build_snapshot(previous, games, pending, params, roster, now, season, source_manifest=None, horizon_days=7):
    """Pure transaction: failure cannot mutate the prior valid snapshot."""
    previous = copy.deepcopy(previous or {})
    now = timestamp(now) if isinstance(now, str) else now
    if now.tzinfo is None:
        raise ValueError('Run time must include a timezone')
    if previous and previous['season'] != season:
        raise ValueError('Live snapshot belongs to another season')
    year = int(season[:4]) + 1
    if any(int(g['season']) != year for g in [*games, *pending]):
        raise ValueError('Wrong season in input records')
    if len({g['game_id'] for g in pending}) != len(pending):
        raise ValueError('Duplicate pending events')
    if {g['game_id'] for g in games} & {g['game_id'] for g in pending}:
        raise ValueError('An event cannot be final and pending')
    old_internal = previous.get('_internal', {})
    if previous.get('published_at') and timestamp(previous['published_at']) > now:
        raise ValueError('Run time moved backwards')
    for source in source_manifest or []:
        if timestamp(source['retrieved_at']) > now:
            raise ValueError('Forecast time precedes source retrieval')
    engine, estimates = rebuild(games, params, roster, now)
    forecasts = copy.deepcopy(old_internal.get('forecasts', []))
    parameters = asdict(params)
    parameter_hash = digest(parameters)
    registry = copy.deepcopy(old_internal.get('parameter_registry', {}))
    registry.setdefault(parameter_hash, {'model_version': MODEL_VERSION, 'parameters': parameters})
    state_hash = digest({'parameters': parameters, 'games': sorted(games, key=lambda g: g['game_id'])})
    corrections = copy.deepcopy(old_internal.get('corrections', []))
    old_games = {g['game_id']: g for g in old_internal.get('games', [])}
    observations = copy.deepcopy(old_internal.get('first_observed_at', {}))
    for g in games:
        identifier = g['game_id']
        observations.setdefault(identifier, now.isoformat())
        if identifier in old_games and digest(g) != digest(old_games[identifier]):
            corrections.append({'game_id': identifier, 'observed_at': now.isoformat(),
                                'previous_sha256': digest(old_games[identifier]), 'current_sha256': digest(g)})
    if set(old_games) - {g['game_id'] for g in games}:
        raise ValueError('Previously completed games cannot silently disappear')
    latest = {}
    for f in forecasts:
        if timestamp(f['issued_at']) >= timestamp(f['start']):
            raise ValueError('Stored forecast was not issued before its scheduled tip')
        latest[f['game_id']] = f
    # Project announced venue/rest routes, but never fabricate future results or ratings.
    planning = copy.deepcopy(engine)
    projected = set()
    upcoming, active_events = [], []
    for g in sorted(pending, key=lambda g: (timestamp(g['start']), g['game_id'])):
        start = timestamp(g['start'])
        if any(g[s]['id'] not in roster for s in ['home', 'away']):
            raise ValueError('Unknown scheduled team')
        if start.astimezone(EASTERN).date() > now.astimezone(EASTERN).date() + timedelta(days=horizon_days):
            continue
        if start > now and g.get('event_state', 'pre') == 'pre':
            row = planning.predict(g)
            signature = digest({'state': state_hash, 'game': g, 'home_context': row['home_context'],
                                'away_context': row['away_context'], 'parameter_hash': parameter_hash})
            if g['game_id'] not in latest or latest[g['game_id']]['input_signature'] != signature:
                row.update(issued_at=now.isoformat(), forecast_cutoff=now.isoformat(),
                           kind='issued_live', forecast_policy_version='after-game-v1', input_signature=signature, parameter_hash=parameter_hash,
                           state_sha256=state_hash, home_id=g['home']['id'], away_id=g['away']['id'],
                           scheduled_context_projected=any(g[s]['id'] in projected for s in ['home', 'away']),
                           eligible_for_evaluation=all(engine.team(g[s]['id']).games >= 10 for s in ['home', 'away']))
                row['forecast_id'] = digest({'game_id': g['game_id'], 'issued_at': row['issued_at'], 'signature': signature})
                forecasts.append(row)
                latest[g['game_id']] = row
            upcoming.append(copy.deepcopy(latest[g['game_id']]))
        else:
            active_events.append({'game_id': g['game_id'], 'start': g['start'],
                                  'home': g['home']['name'], 'away': g['away']['name']})
        for side in ['home', 'away']:
            t = planning.team(g[side]['id'])
            if t.last_start and timestamp(t.last_start) >= start:
                raise ValueError('Invalid announced team chronology')
            t.last_start, t.last_location = g['start'], g['location']
            projected.add(g[side]['id'])
    past = []
    for g in sorted(games, key=lambda g: (timestamp(g['start']), g['game_id'])):
        estimate = estimates[g['game_id']]
        candidates = [f for f in forecasts if f['game_id'] == g['game_id']
                      and f['home_id'] == g['home']['id'] and f['away_id'] == g['away']['id']
                      and timestamp(f['issued_at']) < timestamp(g['start'])]
        issued = max(candidates, key=lambda f: timestamp(f['issued_at'])) if candidates else None
        row = copy.deepcopy(issued or estimate)
        row.update(home_win=estimate['home_win'], home_score=estimate['home_score'], away_score=estimate['away_score'],
                   home_rating_after=estimate['home_rating_after'], away_rating_after=estimate['away_rating_after'],
                   kind='issued_live' if issued else 'unforecasted_backfill')
        if not issued:
            row.update(home_probability=None, away_probability=None, eligible_for_evaluation=False)
        past.append(row)
    scored = [r for r in past if r['kind'] == 'issued_live' and r['eligible_for_evaluation']]
    all_issued = [r for r in past if r['kind'] == 'issued_live']
    rankings = sorted([{'team_id': k, 'team': roster[k], 'elo': t.rating, 'games': t.games, 'wins': t.wins}
                       for k, t in engine.teams.items()], key=lambda r: (-r['elo'], r['team']))
    return {'schema_version': 1, 'season': season, 'status': 'live', 'published_at': now.isoformat(),
            'coverage': {'start': str(min(timestamp(g['start']) for g in games).astimezone(EASTERN).date()) if games else None,
                         'end': str(max(timestamp(g['start']) for g in games).astimezone(EASTERN).date()) if games else None,
                         'parsed': len(games), 'failures': []},
            'result': {'status': 'live_forecasts', 'model_version': MODEL_VERSION, 'parameters': parameters,
                       'metrics': metrics(scored), 'metrics_all_issued': metrics(all_issued),
                       'rankings': rankings, 'predictions': past, 'warmup_games': 10},
            'upcoming': upcoming, 'awaiting_final': active_events,
            '_internal': {'roster': roster, 'games': games, 'pending': pending, 'forecasts': forecasts,
                          'parameter_registry': registry, 'first_observed_at': observations, 'corrections': corrections,
                          'latest_sources': source_manifest or [], 'state_sha256': state_hash,
                          'policy': 'Source-completion event replay for rating state; observed runs issue upcoming revisions. No historical forecast fabrication.'}}
