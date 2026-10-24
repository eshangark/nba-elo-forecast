"""Research-only rating replay and identical training-only probability/margin heads."""
import math
from dataclasses import replace
from itertools import groupby
from statistics import mean

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from nba_forecast.model import Engine, Parameters, slate_date, timestamp
from nba_forecast.replay import slate_cutoff


class LeadEngine(Engine):
    """Reuse canonical update bookkeeping and SOS/performance with k0+k1*L."""
    def __init__(self, params, lead_rate):
        super().__init__(params)
        if not math.isfinite(lead_rate) or lead_rate < 0:
            raise ValueError('Invalid independent lead rate')
        self.lead_rate = lead_rate

    def update(self, game, prediction):
        original = self.params
        peak = max(game['home']['largest_lead'], game['away']['largest_lead'])
        if peak <= 0:
            raise ValueError('Invalid largest lead')
        ratio = abs(game['home']['points']-game['away']['points'])/peak
        self.params = replace(original, k=original.k+self.lead_rate*ratio, lead_weight=0)
        try:
            super().update(game, prediction)
        finally:
            self.params = original


def parameters(fit, challenger=False):
    v = fit['vector']
    weights = np.exp(np.r_[v[7:14], 0]-max(0, max(v[7:14])))
    weights /= weights.sum()
    return Parameters(k=v[0], home_advantage=v[1], fatigue_weight=v[2],
                      travel_weight=10**v[3], lead_weight=0 if challenger else v[4],
                      performance_weight=v[5], schedule_weight=v[6],
                      alpha_weights=tuple(weights))


def replay_seasons(seasons, params, lead_rate=None):
    """All forecasts on a slate precede all its updates, matching production."""
    output, prior = [], {}
    for season, games in sorted(seasons.items()):
        games = sorted(games, key=lambda g: (timestamp(g['start']), g['game_id']))
        if not games or len({g['game_id'] for g in games}) != len(games):
            raise ValueError('Empty season or duplicate games')
        engine = Engine(params) if lead_rate is None else LeadEngine(params, lead_rate)
        for team in {g[s]['id'] for g in games for s in ['home', 'away']}:
            engine.team(team).rating = 1500+.5*(prior.get(team, 1500)-1500)
        last_completion = None
        for day, batch in groupby(games, slate_date):
            batch = list(batch); cutoff = slate_cutoff(day, batch)
            if last_completion and last_completion >= cutoff:
                raise ValueError('Previous slate unavailable at cutoff')
            ids = [g[s]['id'] for g in batch for s in ['home', 'away']]
            if len(ids) != len(set(ids)):
                raise ValueError('Team appears twice on a slate')
            forecasts = [engine.predict(g) for g in batch]
            for g, row in zip(batch, forecasts):
                row.update(season=season, date=str(day), forecast_cutoff=cutoff.isoformat(),
                           home_win=int(g['home']['points'] > g['away']['points']),
                           home_id=g['home']['id'], away_id=g['away']['id'],
                           margin=g['home']['points']-g['away']['points'],
                           venue=int(not g['neutral']), kind='rating_quality_research',
                           eligible_for_evaluation=all(engine.team(g[s]['id']).games >= 10 for s in ['home', 'away']))
                output.append(row)
            for g, row in zip(batch, forecasts):
                engine.update(g, row)
            engine.recenter()
            last_completion = max(timestamp(g['last_play_at']) for g in batch)
        prior = {k: t.rating for k, t in engine.teams.items()}
    return output


def design(rows):
    # Rating gap and venue only: separates ratings from the original context link.
    return np.array([[1, (r['home_rating']-r['away_rating'])/100, r['venue']] for r in rows], dtype=float)


def fit_heads(rows):
    x = design(rows); y = np.array([r['home_win'] for r in rows])
    def objective(w):
        z = x@w
        return np.sum(np.logaddexp(0, z)-y*z)+.5*np.sum(w[1:]**2)
    def gradient(w):
        return x.T@(expit(x@w)-y)+np.r_[0, w[1:]]
    fitted = minimize(objective, np.zeros(3), jac=gradient, method='BFGS', options={'gtol': 1e-6})
    if not fitted.success and np.max(np.abs(gradient(fitted.x))) > 1e-4:
        raise ValueError(f'Probability head failed: {fitted.message}')
    margin = np.linalg.lstsq(x, np.array([r['margin'] for r in rows]), rcond=None)[0]
    return {'probability_coefficients': fitted.x.tolist(), 'margin_coefficients': margin.tolist(),
            'training_games': len(rows), 'l2_penalty': 1.0,
            'training_last_start': max(r['start'] for r in rows)}


def apply_heads(rows, heads):
    if any(timestamp(r['forecast_cutoff']) <= timestamp(heads['training_last_start']) for r in rows):
        raise ValueError('Head training overlaps evaluation cutoff')
    x = design(rows)
    probabilities = expit(x@heads['probability_coefficients'])
    margins = x@heads['margin_coefficients']
    return [{**r, 'home_probability': float(p), 'away_probability': float(1-p),
             'predicted_margin': float(m)} for r, p, m in zip(rows, probabilities, margins)]


def rating_scores(rows):
    errors = [r['predicted_margin']-r['margin'] for r in rows]
    # Consecutive, nonoverlapping ten-game future blocks per team and season.
    teams = {}
    for r in rows:
        for side, y, p in [('home', r['home_win'], r['home_probability']),
                           ('away', 1-r['home_win'], 1-r['home_probability'])]:
            teams.setdefault((r['season'], r[side+'_id']), []).append((p, y))
    blocks = []
    for values in teams.values():
        for i in range(0, len(values)-9, 10):
            block = values[i:i+10]
            blocks.append(sum(p-y for p, y in block))
    return {'margin_mae': mean(abs(e) for e in errors),
            'margin_rmse': math.sqrt(mean(e*e for e in errors)),
            'team_ten_game_blocks': len(blocks),
            'team_ten_game_wins_rmse': math.sqrt(mean(e*e for e in blocks)) if blocks else None,
            'team_block_policy': 'Rolling pregame forecasts summed over nonoverlapping ten-game blocks; incomplete tails omitted. Not a frozen ten-game-ahead forecast.'}


def paired_intervals(candidate, baseline, draws=2000, seed=42):
    """Exploratory whole-slate paired bootstrap, candidate minus baseline."""
    if [r['game_id'] for r in candidate] != [r['game_id'] for r in baseline]:
        raise ValueError('Paired games differ')
    def scores(r):
        p = np.clip(r['home_probability'], 1e-12, 1-1e-12); y = r['home_win']
        return np.array([-(y*np.log(p)+(1-y)*np.log1p(-p)), (p-y)**2,
                         float((p >= .5) == y), abs(r['predicted_margin']-r['margin'])])
    slates = {}
    for a, b in zip(candidate, baseline):
        if (a['home_win'], a['date']) != (b['home_win'], b['date']):
            raise ValueError('Paired outcomes or dates differ')
        slates.setdefault(a['date'], []).append(scores(a)-scores(b))
    totals = np.array([np.sum(v, axis=0) for v in slates.values()]); counts = np.array([len(v) for v in slates.values()])
    rng = np.random.default_rng(seed); samples = []
    for _ in range(draws):
        index = rng.integers(0, len(counts), len(counts))
        samples.append(totals[index].sum(axis=0)/counts[index].sum())
    bounds = np.quantile(samples, [.025, .975], axis=0)
    point = totals.sum(axis=0)/counts.sum()
    return {key: {'difference': float(point[i]), 'lower_95': float(bounds[0, i]), 'upper_95': float(bounds[1, i])}
            for i, key in enumerate(['log_loss', 'brier_score', 'winner_accuracy', 'margin_mae'])}
