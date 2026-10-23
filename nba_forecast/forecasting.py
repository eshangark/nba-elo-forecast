"""Causal player/team histories and portable probability models.

These models adjust published probabilities, never the residual used by Elo.
The runtime uses only the standard library; tree training remains optional.
"""

import copy
import hashlib
import json
import math
from datetime import date
from zoneinfo import ZoneInfo

from .model import box_features, logistic, slate_date, timestamp

INJURY_FEATURES = [f'{side}_{kind}' for side in ['out', 'doubtful', 'questionable', 'probable']
                   for kind in ['minutes', 'value']]
INJURY_FEATURES += ['submitted_difference', 'unmapped_difference', 'no_history_difference', 'valued_players_difference',
                    'home_submitted', 'home_unmapped', 'home_no_history',
                    'away_submitted', 'away_unmapped', 'away_no_history']
TEAM_FEATURES = ['rest_difference', 'back_to_back_difference', 'four_day_load_difference',
                 'travel_difference_1000km', 'signed_timezone_difference', 'absolute_timezone_difference',
                 'home_rest', 'away_rest']
TEAM_FEATURES += [f'{kind}_half_{half}' for half in [5, 10, 20] for kind in ['net_efficiency', 'adjusted_margin']]
TEAM_FEATURES += [f'prior_box_{i}' for i in range(1, 9)] + ['points_for', 'points_against', 'possessions']
TEAM_FEATURES += ['rotation_overlap', 'returning_minutes', 'missing_leaders', 'rotation_history_known',
                 'previous_season_known', 'last_rotation_known']


def log_odds(p):
    if not math.isfinite(p) or not 0 < p < 1:
        raise ValueError('Probability must be finite and strictly between zero and one')
    return math.log(p) - math.log1p(-p)


def carryover_ratings(previous, roster, fraction=0.5):
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError('Invalid carryover fraction')
    if set(previous) - set(roster):
        raise ValueError('Carryover contains an unknown team')
    result = {t: 1500 + fraction * (previous.get(t, 1500) - 1500) for t in roster}
    if not all(math.isfinite(v) for v in result.values()):
        raise ValueError('Invalid prior rating')
    shift = sum(result.values()) / len(result) - 1500
    return {t: v-shift for t, v in result.items()}


class FeatureState:
    """JSON-serializable prior-only histories, including cross-season player value."""

    def __init__(self, saved=None):
        self.data = copy.deepcopy(saved) if saved else {
            'season': None, 'form': {}, 'player_history': {}, 'season_minutes': {},
            'previous_season_minutes': {}, 'last_rotation': {}, 'before_rotation': {},
            'game_dates': {}, 'last_location': {}, 'observed_games': []}

    def start_season(self, season):
        if self.data['season'] == season:
            return
        if self.data['season'] and season <= self.data['season']:
            raise ValueError('Feature season cannot move backwards')
        self.data.update(season=season, previous_season_minutes=self.data['season_minutes'],
                         season_minutes={}, last_rotation={}, before_rotation={}, game_dates={}, last_location={})

    def injury_features(self, game, reports):
        vectors, coverage = [], []
        for side in ['home', 'away']:
            x = [0.] * 12
            report = reports.get(game[side]['id'])
            submitted = bool(report and report['submitted'])
            x[8] = float(submitted)
            coverage.append('submitted' if submitted else 'not_submitted' if report else 'unavailable')
            if submitted:
                for row in report['players']:
                    athlete = row.get('athlete')
                    history = self.data['player_history'].get(athlete)
                    if athlete is None:
                        x[9] += 1
                    if history is None:
                        x[10] += 1
                        continue
                    if row['status'] not in ['Out', 'Doubtful', 'Questionable', 'Probable']:
                        continue
                    j = ['Out', 'Doubtful', 'Questionable', 'Probable'].index(row['status'])
                    minutes = history[0] / history[1]
                    value = (history[2] + 80*.3) / (history[0] + 80)
                    x[2*j] += minutes / 240
                    x[2*j+1] += minutes * value / 80
                    x[11] += 1
            vectors.append(x)
        return ([a-b for a, b in zip(*vectors)] + vectors[0][8:11] + vectors[1][8:11], coverage)

    def team_features(self, game, prediction):
        forms, boxes, rotations, shifts, loads = [], [], [], [], []
        day = slate_date(game)
        for side in ['home', 'away']:
            team = game[side]['id']
            histories = self.data['form'].get(team, {})
            form = []
            for half in [5, 10, 20]:
                h = histories.get(str(half))
                form.extend([h[0][j]/h[1] for j in range(2)] if h else [0., 0.])
            h = histories.get('10')
            forms.append(form)
            boxes.append([v/h[1] for v in h[0][2:]] if h else [0.] * 11)
            current = self.data['last_rotation'].get(team)
            prior = self.data['before_rotation'].get(team)
            previous = self.data['previous_season_minutes'].get(team, {})
            if current:
                cm, pm = sum(current.values()), sum(prior.values()) if prior else 1
                overlap = sum(min(v/cm, prior.get(a, 0)/pm) for a, v in current.items()) if prior else 0
                returning = sum(v for a, v in current.items() if a in previous)/cm if previous else 0
                totals = self.data['season_minutes'].get(team, {})
                leaders = sorted(totals, key=totals.get, reverse=True)[:3]
                missing = sum(totals[a] for a in leaders if a not in current)/max(1, sum(totals[a] for a in leaders))
                rotations.append([overlap, returning, missing, float(bool(prior)), float(bool(previous)), 1.])
            else:
                rotations.append([0.] * 6)
            previous_location = self.data['last_location'].get(team)
            tip = timestamp(game['start'])
            shift = 0. if previous_location is None else (
                tip.astimezone(ZoneInfo(game['location']['timezone'])).utcoffset()
                - tip.astimezone(ZoneInfo(previous_location['timezone'])).utcoffset()).total_seconds()/3600
            shifts.append(shift)
            loads.append(sum(0 < (day-date.fromisoformat(past)).days < 4
                             for past in self.data['game_dates'].get(team, [])))
        home, away = prediction['home_context'], prediction['away_context']
        schedule = [min(home['rest'], 7)-min(away['rest'], 7), float(home['rest'] == 0)-float(away['rest'] == 0),
                    loads[0]-loads[1], (home['travel']-away['travel'])/1000,
                    shifts[0]-shifts[1], abs(shifts[0])-abs(shifts[1]), min(home['rest'], 7), min(away['rest'], 7)]
        return schedule + [a-b for pair in [forms, boxes, rotations] for a, b in zip(*pair)]

    def observe(self, game, base_probability, players=None):
        if game['game_id'] in self.data['observed_games']:
            raise ValueError('Duplicate feature-history game')
        self.data['observed_games'].append(game['game_id'])
        residual = game['home']['points']-game['away']['points']-7.5*log_odds(base_probability)
        for side, other, sign in [('home', 'away', 1), ('away', 'home', -1)]:
            team = game[side]['id']
            features = box_features(game[side], game[other])
            poss = game[side]['fga']+.44*game[side]['fta']-game[side]['oreb']+game[side]['tov']
            current = [features[0], sign*residual, *features, game[side]['points'], game[other]['points'], poss]
            histories = self.data['form'].setdefault(team, {})
            for half in [5, 10, 20]:
                old = histories.get(str(half), [[0.]*13, 0.])
                decay = 2**(-1/half)
                histories[str(half)] = [[decay*a+b for a, b in zip(old[0], current)], decay*old[1]+1]
            self.data['last_location'][team] = game['location']
            self.data['game_dates'].setdefault(team, []).append(str(slate_date(game)))
            rows = (players or {}).get(team)
            self.data['before_rotation'][team] = self.data['last_rotation'].get(team)
            if rows is None:
                self.data['last_rotation'][team] = None
                continue
            rotation = {row['athlete']: row['minutes'] for row in rows}
            self.data['last_rotation'][team] = rotation
            totals = self.data['season_minutes'].setdefault(team, {})
            for row in rows:
                athlete, minutes, value = row['athlete'], row['minutes'], row['game_score']
                if not all(math.isfinite(v) for v in [minutes, value]) or minutes <= 0:
                    raise ValueError('Invalid player feature update')
                old = self.data['player_history'].get(athlete, [0., 0., 0.])
                self.data['player_history'][athlete] = [2**(-1/10)*a+b for a, b in zip(old, [minutes, 1., value])]
                totals[athlete] = totals.get(athlete, 0)+minutes

    def project_schedule(self, game):
        """Announced travel/workload only; never invent box scores or player minutes."""
        for side in ['home', 'away']:
            team = game[side]['id']
            self.data['last_location'][team] = game['location']
            self.data['game_dates'].setdefault(team, []).append(str(slate_date(game)))


def ridge_probability(model, features, base_probability):
    if model.get('unchanged_base'):
        return base_probability
    if len(features) != len(model['means']) or len(model['weights']) != len(features)+1:
        raise ValueError('Probability feature schema mismatch')
    z = log_odds(base_probability)+model['weights'][0]
    for value, mean, scale, weight in zip(features, model['means'], model['scales'], model['weights'][1:]):
        if not all(math.isfinite(v) for v in [value, mean, scale, weight]) or scale <= 0:
            raise ValueError('Invalid standardized feature')
        z += weight*(value-mean)/scale
    return logistic(z)


def tree_probability(model, features, base_probability):
    if model.get('unchanged_base'):
        return base_probability
    score = model['intercept']
    for nodes in model['trees']:
        node = nodes[0]
        for _ in range(len(nodes)):
            if node['leaf']:
                score += node['value']
                break
            value = features[node['feature']]
            node = nodes[node['left'] if value <= node['threshold'] else node['right']]
        else:
            raise ValueError('Tree contains a cycle')
    weight = model['blend']
    return (1-weight)*base_probability+weight*logistic(score)


class Forecaster:
    def __init__(self, bundle):
        self.bundle = copy.deepcopy(bundle)
        self.fingerprint = hashlib.sha256(json.dumps(bundle, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if bundle['feature_schema'] != {'injury': ['base_logit']+INJURY_FEATURES,
                                        'boosted': ['base_logit']+TEAM_FEATURES+INJURY_FEATURES}:
            raise ValueError('Unsupported forecast feature schema')

    def predict(self, game, base, state, reports=None, report_source=None):
        p = base['home_probability']
        injury, coverage = state.injury_features(game, reports or {})
        z = log_odds(p)
        # Missing collection/too-early schedules use an explicit unchanged-Elo fallback.
        usable = bool(report_source and any(team in (reports or {}) for team in [game['home']['id'], game['away']['id']]))
        if usable:
            adjusted = ridge_probability(self.bundle['injury_head'], [z]+injury, p)
            boosted_features = [z]+state.team_features(game, base)+injury
            boosted = tree_probability(self.bundle['boosted_head'], boosted_features, p)
            status = 'complete' if coverage == ['submitted', 'submitted'] else 'partial_or_unsubmitted'
        else:
            adjusted, boosted, status = p, p, 'elo_fallback'
        variants = {}
        for key, value in [('base', p), ('injury', adjusted), ('boosted', boosted)]:
            if not math.isfinite(value) or not 0 < value < 1:
                raise ValueError('Invalid published probability')
            variants[key] = {'home_probability': value, 'away_probability': 1-value,
                             'model_version': self.bundle['version']+'/'+key,
                             'status': 'carryover_elo' if key == 'base' else status}
        return {'home_probability': adjusted, 'away_probability': 1-adjusted,
                'base_home_probability': p, 'base_away_probability': 1-p,
                'probability_models': variants, 'model_version': self.bundle['version'],
                'forecast_model_sha256': self.fingerprint, 'injury_coverage': {'home': coverage[0], 'away': coverage[1]},
                'injury_source': report_source if usable else None,
                'forecast_features': {'injury': [z]+injury, 'boosted': boosted_features} if usable else None,
                'injury_status': status}
