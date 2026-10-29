"""Plain-language matchup context and exact sequential forecast explanations."""
import json
import math
from pathlib import Path

from .forecasting import INJURY_FEATURES
from .model import EASTERN, logistic, timestamp
from .accuracy_data import current_view_matches


def elo_ranks(rankings):
    return {row['team']: 1+sum(other['elo'] > row['elo'] for other in rankings) for row in rankings}


def previous_seasons(archives, entries, season, fingerprint=None):
    result = []
    for entry in sorted((e for e in entries if e['season'] < season and e.get('file')), key=lambda e:e['season'], reverse=True)[:3]:
        archive = json.loads((Path(archives)/entry['file']).read_text())
        view = archive['result']
        candidate_path = Path(archives)/entry['season']/'current-model.json'
        if candidate_path.exists():
            candidate = json.loads(candidate_path.read_text())
            index_path = Path(archives)/'current-model-index.json'
            index = json.loads(index_path.read_text()) if index_path.exists() else None
            if current_view_matches(archive, candidate, fingerprint, index):
                view = candidate['result']
        result.append({'season': entry['season'], 'ranks': elo_ranks(view['rankings']), 'rankings': view['rankings']})
    return result


def recent_record(team, rows, before, completions=None):
    games = [r for r in rows if team in (r['home'], r['away'])
             and timestamp((completions or {}).get(r['game_id'], r['start'])) < timestamp(before)]
    games = sorted(games, key=lambda r:(timestamp(r['start']),r['game_id']))[-10:]
    wins = sum(bool(r['home_win']) if r['home'] == team else not bool(r['home_win']) for r in games)
    return {'games':len(games), 'wins':wins, 'losses':len(games)-wins,
            'label':f'{wins}–{len(games)-wins} ({len(games)} played)' if games else 'No games yet'}


def team_game_history(team, rows):
    """Completed season games, newest first, from the selected team's perspective."""
    history = []
    for row in sorted(rows, key=lambda r: (timestamp(r['start']), r['game_id']), reverse=True):
        side = 'home' if row['home'] == team else 'away' if row['away'] == team else None
        if side is None or any(row.get(key) is None for key in ('home_score', 'away_score', 'home_win')):
            continue
        opponent = 'away' if side == 'home' else 'home'
        won = bool(row['home_win']) if side == 'home' else not bool(row['home_win'])
        history.append({
            'Date': timestamp(row['start']).astimezone(EASTERN).date(),
            'Opponent': row[opponent],
            'Home / Away': side.title(),
            'Result': 'W' if won else 'L',
            'Score': f"{row[side + '_score']}–{row[opponent + '_score']}",
            'Elo after': row.get(side + '_rating_after'),
            'Elo change': row.get(side + '_rating_change'),
        })
    return history


def injury_label(row):
    return {'complete':'Both reports submitted', 'partial_or_unsubmitted':'Reports incomplete',
            'elo_fallback':'No report · base Elo'}.get(row.get('injury_status'), 'Report information unavailable')


def probability_steps(row, parameters):
    required = ['c','home_advantage','fatigue_weight','travel_weight']
    if any(key not in parameters for key in required) or 'base_home_probability' not in row:
        return []
    p = parameters; difference = row['home_rating']-row['away_rating']
    first = logistic(math.log(10)*difference/p['c'])
    hc, ac = row['home_context'], row['away_context']
    ortf = ac['rest']+math.exp(abs(hc['timezone_change'])/3)+p['travel_weight']*hc['travel']
    trof = hc['rest']+math.exp(abs(ac['timezone_change'])/3)+p['travel_weight']*ac['travel']
    # Infer the applied home bonus from stored base log odds. Neutral games
    # have zero bonus; do not assume every home-listed game is at home.
    base = row['base_home_probability']
    if not 0 < base < 1:
        return []
    bonus = p['c']*(math.log(base/(1-base))/math.log(10)+p['fatigue_weight']*math.log(ortf/trof))-difference
    if not (abs(bonus) < 1e-7 or abs(bonus-p['home_advantage']) < 1e-7):
        return []
    second = logistic(math.log(10)*(difference+bonus)/p['c'])
    third = logistic(math.log(10)*((difference+bonus)/p['c']-p['fatigue_weight']*math.log(ortf/trof)))
    if abs(third-base) > 1e-10:
        return []
    stages = [('Ratings only',first),('Add home court' if abs(bonus)>1e-7 else 'Zero home-court adjustment',second),
              ('Add rest / travel',base),('Injury inputs + fitted recalibration',row['home_probability'])]
    return [{'Stage':name,'Home win %':value*100,'Change (pp)':None if i==0 else (value-stages[i-1][1])*100}
            for i,(name,value) in enumerate(stages)]


def data_gaps(row, rankings):
    by_name = {r['team']:r for r in rankings}; messages = []
    for name in [row['home'],row['away']]:
        played = by_name.get(name,{}).get('games')
        if played is None:
            messages.append(f'{name}: current-season game count at the forecast cutoff is unavailable.')
        elif played < 10:
            messages.append(f'{name}: only {played} current-season games; ratings still depend substantially on prior-season carryover.')
    if row.get('injury_status') != 'complete':
        messages.append(injury_label(row)+'. Missing reports do not mean healthy players.')
    features = (row.get('forecast_features') or {}).get('injury')
    if features and len(features) == 19:
        values = dict(zip(INJURY_FEATURES,features[1:]))
        for side in ['home','away']:
            missing = values[f'{side}_no_history']; unmatched = values[f'{side}_unmapped']
            if missing or unmatched:
                messages.append(f'{row[side]}: {int(unmatched)} unmatched report names; {int(missing)} players without prior histories (counts can overlap).')
    if row.get('scheduled_context_projected'):
        messages.append('Rest/travel includes announced intervening games; their results and lineups are not known.')
    messages.append('Current-game lineups and complete roster-change effects are not modeled. A previous-season rank is context, not a guarantee of current strength.')
    return messages


def issued_rows(archive):
    return [r for r in archive.get('result',{}).get('predictions',[]) if r.get('kind') == 'issued_live' and r.get('home_probability') is not None]
