"""Fetch observed NBA records and atomically publish a current-season snapshot."""

import argparse
import json
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_forecast.data import Cities, Client, parse_summary, write_json
from nba_forecast.live import build_snapshot, event_kind, parse_schedule, live_lock
from nba_forecast.model import EASTERN, Parameters, timestamp
from nba_forecast.seasons import current_season
from nba_forecast.validation import validate_game


def collect(client, cities, previous, season, run_started, horizon_days=7, full_refresh=False):
    today = run_started.astimezone(EASTERN).date()
    year = int(season[:4]) + 1
    anchor = client.get('scoreboard', f'dates={today:%Y%m%d}&limit=1000', refresh=True)
    leagues = [l for l in anchor['leagues'] if str(l['id']) == '46']
    if len(leagues) != 1 or int(leagues[0]['season']['year']) != year:
        raise ValueError('Provider calendar does not match the requested NBA season')
    league = leagues[0]
    internal = (previous or {}).get('_internal', {})
    season_start = timestamp(league['season']['startDate']).astimezone(EASTERN).date()
    start = season_start if full_refresh or not internal else max(season_start, today-timedelta(days=7))
    end = today + timedelta(days=horizon_days)
    if league.get('calendarIsWhitelist') and league.get('calendarType') == 'day':
        days = {timestamp(d).astimezone(EASTERN).date() for d in league['calendar']}
        days = {d for d in days if start <= d <= end}
    else:
        days = {start + timedelta(days=i) for i in range((end-start).days+1)}
    days.add(today)
    # Revisit unresolved events even if their old scheduled dates have left the lookback.
    days.update(timestamp(g['start']).astimezone(EASTERN).date() for g in internal.get('pending', [])
                if timestamp(g['start']).astimezone(EASTERN).date() <= end)
    events = {}
    for i, day in enumerate(sorted(days), 1):
        payload = anchor if day == today else client.get('scoreboard', f'dates={day:%Y%m%d}&limit=1000', refresh=True)
        if 'events' not in payload or len(payload['events']) >= 1000:
            raise ValueError('Incomplete or potentially truncated scoreboard')
        for e in payload['events']:
            identifier = str(e['id'])
            if identifier in events and events[identifier] != e:
                raise ValueError('Conflicting duplicate schedule events')
            events[identifier] = e
        if i % 5 == 0:
            print(f'Checked {i}/{len(days)} schedule dates', flush=True)
    completed = {g['game_id']: g for g in internal.get('games', [])}
    missing = [g['game_id'] for g in completed.values()
               if timestamp(g['start']).astimezone(EASTERN).date() in days and g['game_id'] not in events]
    if missing:
        raise ValueError(f'Provider omitted known completed events: {missing}')
    pending, exclusions = [], []
    for identifier, event in sorted(events.items()):
        kind = event_kind(event, year)
        if kind in {'excluded', 'inactive'}:
            if identifier in completed:
                raise ValueError('Previously final game changed to an unsupported status')
            exclusions.append({'game_id': identifier, 'reason': kind})
            continue
        if kind == 'final':
            game = parse_summary(client.get('summary', 'event='+identifier, refresh=True), cities)
            validate_game(game)
            if game['game_id'] != identifier or game['season'] != year:
                raise ValueError('Scoreboard/summary identity mismatch')
            c = event['competitions'][0]
            counterparts = {x['homeAway']: x for x in c['competitors']}
            for side in ['home', 'away']:
                if game[side]['id'] != str(counterparts[side]['team']['id']) or game[side]['points'] != int(counterparts[side]['score']):
                    raise ValueError('Scoreboard/summary outcome mismatch')
            completed[identifier] = game
        else:
            if identifier in completed:
                raise ValueError('Previously final game returned as unfinished')
            pending.append(parse_schedule(event, cities))
    return list(completed.values()), pending, {'dates_checked': [str(d) for d in sorted(days)],
                                              'event_count': len(events), 'exclusions': exclusions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cities', required=True, type=Path)
    parser.add_argument('--cache', type=Path, default=Path('data/raw/live-espn'))
    parser.add_argument('--archives', type=Path, default=Path('data/seasons'))
    parser.add_argument('--parameters', type=Path, default=Path('models/nba-v0.2/parameters.json'))
    parser.add_argument('--horizon-days', type=int, default=7, choices=range(1, 15))
    parser.add_argument('--full-refresh', action='store_true', help='Recheck every current-season calendar date')
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    season = current_season(started.astimezone(EASTERN).date())
    with live_lock(args.archives):
        run_update(args, started, season)


def run_update(args, started, season):
    directory = args.archives / season
    live_path, status_path = directory/'live.json', directory/'update_status.json'
    previous = json.loads(live_path.read_text()) if live_path.exists() else None
    try:
        index = json.loads((args.archives/'index.json').read_text())
        if previous:
            roster = previous['_internal']['roster']
        else:
            seed_path = directory/'snapshot.json'
            if seed_path.exists():
                seed = json.loads(seed_path.read_text())
                roster = {t['team_id']: t['team'] for t in seed['teams']}
            else:
                prior = sorted([e for e in index['seasons'] if e['season'] < season and e.get('file')],
                               key=lambda e: e['season'], reverse=True)
                if not prior:
                    raise ValueError('No verified roster available for season initialization')
                from nba_forecast.seasons import load_season
                seed = load_season(args.archives, prior[0])
                teams = seed.get('teams') or seed['result']['rankings']
                roster = {t['team_id']: t['team'] for t in teams}
        params = Parameters(**json.loads(args.parameters.read_text()))
        client, cities = Client(args.cache), Cities(args.cities)
        games, pending, coverage = collect(client, cities, previous, season, started,
                                          args.horizon_days, args.full_refresh)
        roster = dict(roster)
        for g in [*games, *pending]:
            for side in ['home', 'away']:
                if g[side]['id'] not in roster:
                    raise ValueError('Unexpected team outside the seeded roster')
                roster[g[side]['id']] = g[side]['name']
        # Issue time is observed AFTER fetching; there is no backdate option.
        snapshot = build_snapshot(previous, games, pending, params, roster, datetime.now(timezone.utc),
                                  season, client.manifest, args.horizon_days)
        snapshot['_internal']['collection'] = coverage
        snapshot['_internal']['geonames_sha256'] = hashlib.sha256(args.cities.read_bytes()).hexdigest()
        write_json(live_path, snapshot)
        index['seasons'] = [e for e in index['seasons'] if e['season'] != season]
        index['seasons'].append({'season': season, 'status': 'live', 'file': f'{season}/live.json'})
        index['seasons'].sort(key=lambda e: e['season'], reverse=True)
        write_json(args.archives/'index.json', index)
        write_json(status_path, {'state': 'success', 'attempted_at': started.isoformat(),
                                 'finished_at': snapshot['published_at'], 'last_successful_at': snapshot['published_at']})
        print(json.dumps({'season': season, 'completed_games': len(games), 'upcoming_forecasts': len(snapshot['upcoming']),
                          'stored_revisions': len(snapshot['_internal']['forecasts']), 'published_at': snapshot['published_at']}, indent=2))
    except Exception as exc:
        write_json(status_path, {'state': 'failed', 'attempted_at': started.isoformat(),
                                 'last_successful_at': previous.get('published_at') if previous else None,
                                 'error': f'{type(exc).__name__}: {exc}'})
        raise


if __name__ == '__main__':
    main()
