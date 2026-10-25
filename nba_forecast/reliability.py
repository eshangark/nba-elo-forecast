"""Observable forecast input checks, separate from win probability or betting value."""
import math
from datetime import timedelta
from .model import timestamp
from .forecasting import INJURY_FEATURES
from .evaluation import favorite_bands


def _time(value):
    try:
        return timestamp(value) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def injury_details(row):
    features = (row.get('forecast_features') or {}).get('injury')
    values = None
    if isinstance(features, list) and len(features) == len(INJURY_FEATURES)+1:
        candidate = dict(zip(INJURY_FEATURES, features[1:]))
        keys = [f'{side}_{kind}' for side in ['home', 'away'] for kind in ['unmapped', 'no_history']]
        if all(isinstance(candidate[k], (int, float)) and math.isfinite(candidate[k]) and candidate[k] >= 0 for k in keys):
            values = candidate
    teams = []
    for side in ['home', 'away']:
        report = (row.get('injury_report') or {}).get(row.get(side+'_id'))
        players = (report or {}).get('players', [])
        # A missing report is unknown, including older rows without captured raw reports.
        submitted = (report.get('submitted') if report is not None else
                     (row.get('injury_coverage') or {}).get(side) == 'submitted')
        unmatched = int(values[side+'_unmapped']) if values else None
        missing = int(values[side+'_no_history']) if values else None
        unresolved = [p.get('name', 'Unnamed player') for p in players
                      if p.get('status') in ['Questionable', 'Doubtful', 'Probable']]
        unrecognized = [p.get('name', 'Unnamed player') for p in players if not p.get('athlete')]
        teams.append({'Team': row[side], 'Report': 'Submitted' if submitted else 'Unknown / unsubmitted',
                      'Unmatched names': unmatched, 'Missing histories': missing,
                      'Unresolved availability': ', '.join(unresolved) if unresolved else
                          ('None listed' if submitted and report is not None else 'Unknown'),
                      'Unmatched players': ', '.join(unrecognized) if unrecognized else
                          ('None listed' if submitted and report is not None else 'Unknown')})
    if row.get('injury_status') == 'elo_fallback':
        label = 'No usable report · base Elo'
    elif row.get('injury_status') != 'complete' or any(t['Report'] != 'Submitted' for t in teams):
        label = 'Reports incomplete'
    elif values is None:
        label = 'Player coverage unverified'
    elif any(t['Unmatched names'] or t['Missing histories'] or t['Unmatched players'] not in ['None listed', 'Unknown'] for t in teams):
        label = 'Player data gaps'
    elif any(t['Unresolved availability'] not in ['None listed', 'Unknown'] for t in teams):
        label = 'Availability unresolved'
    elif any(t['Unresolved availability'] == 'Unknown' for t in teams):
        label = 'Availability unverified'
    else:
        label = 'Captured inputs complete'
    return {'label': label, 'teams': teams}


def forecast_reliability(row, predictions, completions, published_at, now):
    """No scores or inferred news: use only captured facts, with explicit ages."""
    current = _time(now); issued = _time(row.get('issued_at') or row.get('forecast_cutoff')); checked = _time(published_at)
    start = _time(row.get('start'))
    def age(when):
        if current is None or when is None or when > current:
            return 'Unknown'
        minutes = int((current-when).total_seconds()/60)
        return f'{minutes}m ago' if minutes < 60 else f'{minutes//60}h {minutes%60}m ago'
    stale = bool(current and checked and current-checked > timedelta(hours=2))
    freshness = ('Timestamp unavailable' if not current or not checked or checked > current else
                 'Snapshot older than 2h' if stale else 'Snapshot checked within 2h')
    if current and start and start <= current:
        freshness = 'Tip-off passed · pregame snapshot'
    # Count all completed season games before issuance, not just the last ten or today's rankings.
    counts = {}
    for name in [row['home'], row['away']]:
        games = [r for r in predictions if name in (r['home'], r['away'])]
        known = [r for r in games if issued and _time(completions.get(r['game_id']))
                 and _time(completions[r['game_id']]) < issued]
        counts[name] = len(known) if issued and all(_time(completions.get(r['game_id'])) for r in games) else None
    maturity = ('Season evidence unknown' if any(v is None for v in counts.values()) else
                'Limited season evidence' if min(counts.values()) < 10 else '10+ prior games per team')
    source = _time((row.get('injury_source') or {}).get('published_at'))
    return {'injury': injury_details(row), 'freshness': freshness, 'snapshot_age': age(checked),
            'forecast_age': age(issued), 'report_age': age(source), 'counts': counts, 'maturity': maturity,
            'report_outdated': bool(current and source and current-source > timedelta(hours=16))}


def calibration_context(row, evidence, before=None, exact_model=False, allow_replay=False):
    """Compare probability bands; replay rows require explicit historical-fit opt-in."""
    p = row['home_probability']; confidence = max(p, 1-p)
    target = min(19, int(math.floor(round(confidence*20, 10))))
    selected = []
    for past in evidence:
        if past.get('kind') not in (['issued_live', 'chronological_backtest', 'current_method_replay'] if allow_replay else ['issued_live', 'chronological_backtest']):
            continue
        if past.get('home_probability') is None or past.get('home_win') not in (0, 1):
            continue
        if exact_model and (not row.get('forecast_model_sha256') or
                            past.get('forecast_model_sha256') != row['forecast_model_sha256']):
            continue
        if before and (not past.get('last_play_at') or timestamp(past['last_play_at']) >= timestamp(before)):
            continue
        selected.append(past)
    return next((band for band in favorite_bands(selected)
                 if min(19, int(math.floor(round(band['mean_forecast']*20, 10)))) == target), None)


def captured_adjustment(row):
    base = row.get('base_home_probability'); final = row.get('home_probability')
    if not all(isinstance(p, (float, int)) and math.isfinite(p) and 0 <= p <= 1 for p in [base, final]):
        return None
    return (final-base)*100


def forecast_dependence(row, rankings):
    """Separate matchup favoritism from absolute strength; reject stale ranks."""
    side = 'home' if row['home_probability'] >= .5 else 'away'
    other = 'away' if side == 'home' else 'home'
    by_name = {r['team']: r for r in rankings}
    valid = all(name in by_name and row.get(s+'_rating') is not None
                and abs(by_name[name]['elo']-row[s+'_rating']) < 1e-8
                for s, name in [(side,row[side]),(other,row[other])])
    rank = opponent_rank = None
    if valid:
        rank = 1+sum(r['elo'] > row[side+'_rating'] for r in rankings)
        opponent_rank = 1+sum(r['elo'] > row[other+'_rating'] for r in rankings)
    base = row.get('base_home_probability')
    base = (base if side == 'home' else 1-base) if base is not None else None
    probability = row[side+'_probability']
    return {'favorite':row[side], 'opponent':row[other], 'favorite_probability':probability,
            'base_probability':base, 'adjustment_pp':(probability-base)*100 if base is not None else None,
            'rank':rank, 'opponent_rank':opponent_rank,
            'strength_label':('Rank at issuance unavailable' if rank is None else
                              'Low-rated favorite' if rank > len(rankings)/2 else 'Upper-half favorite')}


def team_calibration_evidence(row, evidence, team, before, exact_model=False, pseudo_count=80, allow_replay=False):
    """Descriptive residual pooling, never a new forecast or confidence percentage."""
    if team not in [row['home'], row['away']] or pseudo_count <= 0:
        raise ValueError('Invalid team or pooling reference')
    probability = row['home_probability'] if team == row['home'] else row['away_probability']
    def index(p):return min(9, int(math.floor(round(p*10,10))))
    target=index(probability); league=[];own=[];own_picks=[];seen=set()
    for past in evidence:
        if past.get('kind') not in (['issued_live', 'chronological_backtest', 'current_method_replay'] if allow_replay else ['issued_live', 'chronological_backtest']):
            continue
        completion=_time(past.get('last_play_at'));cutoff=_time(before)
        if completion is None or cutoff is None or completion >= cutoff:
            continue
        if exact_model and (not row.get('forecast_model_sha256') or
                            past.get('forecast_model_sha256') != row['forecast_model_sha256']):
            continue
        p=past.get('home_probability');y=past.get('home_win')
        if not isinstance(p,(float,int)) or not math.isfinite(p) or not 0<=p<=1 or y not in [0,1]:
            raise ValueError('Invalid calibration evidence')
        identifier=past.get('game_id')
        if identifier is not None:
            if identifier in seen:raise ValueError('Duplicate calibration game')
            seen.add(identifier)
        for name, chance, outcome in [(past['home'],p,y),(past['away'],1-p,1-y)]:
            if index(chance)==target:
                league.append((chance,outcome))
                if name==team:
                    own.append((chance,outcome))
                    own_picks.append(int(p >= .5) == y)
    n=len(own);reference=sum(y-p for p,y in league)/len(league) if league else None
    raw=sum(y-p for p,y in own)/n if n else None
    pooled=(sum(y-p for p,y in own)+pseudo_count*reference)/(n+pseudo_count) if reference is not None else None
    interval = None
    if n:
        rate=sum(y for p,y in own)/n;z=1.959963984540054;denominator=1+z*z/n
        center=(rate+z*z/(2*n))/denominator
        radius=z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/denominator
        interval=f'{center-radius:.1%}–{center+radius:.1%}'
    return {'team':team,'band':f'{target*10}–{(target+1)*10}%', 'games':n,
            'wins':sum(y for p,y in own),
            'winner_accuracy':sum(own_picks)/n if n else None,
            'observed_rate_interval_95':interval,
            'mean_forecast':sum(p for p,y in own)/n if n else None,
            'observed_win_rate':sum(y for p,y in own)/n if n else None,
            'raw_error_pp':raw*100 if raw is not None else None,
            'pooled_error_pp':pooled*100 if pooled is not None else None,
            'reference_appearances':len(league),'pooling_reference':pseudo_count,
            'sample_label':'No team evidence' if n==0 else 'Small sample' if n<30 else 'Read with sampling uncertainty'}


def player_impact_evidence(row, internal):
    """Only use saved player history when the forecast's state is still identical."""
    same_state=bool(row.get('state_sha256') and row['state_sha256']==internal.get('state_sha256'))
    histories=internal.get('feature_state',{}).get('player_history',{}) if same_state else {}
    output=[]
    for side in ['home','away']:
        report=(row.get('injury_report') or {}).get(row.get(side+'_id'))
        if not report or not report.get('submitted'):continue
        for player in report.get('players',[]):
            h=histories.get(player.get('athlete'))
            known=bool(h and len(h)==3 and all(isinstance(x,(int,float)) and math.isfinite(x) for x in h)
                       and h[0]>=0 and h[1]>0)
            minutes=h[0]/h[1] if known else None
            value=(h[2]+24)/(h[0]+80) if known else None
            output.append({'Team':row[side], 'Player':player.get('name','Name unavailable'),
                           'Status':player.get('status','Unknown'), 'Expected minutes':minutes,
                           'Game Score / minute':value,
                           'Prior contribution proxy':minutes*value if known else None,
                           'History':'Prior history available' if known else 'History at issuance unavailable'})
    return output
