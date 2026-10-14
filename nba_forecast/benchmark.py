"""Fitted simple Elo comparator and paired daily-slate uncertainty estimates."""

from dataclasses import asdict

import numpy as np
from scipy.optimize import differential_evolution

from .fitting import decode, initial_vector, loss, prepare, probabilities
from .model import slate_date
from .replay import replay

SIMPLE_BOUNDS = [(1, 80), (0, 180)]


def simple_vector(k, home_advantage):
    vector = initial_vector()
    vector[0], vector[1] = k, home_advantage
    vector[2] = vector[4] = vector[5] = vector[6] = 0.0
    return vector


def fit_simple(training_seasons, seed=42, maxiter=150, warmup=10):
    prepared = [prepare(g, warmup) for g in training_seasons]
    result = differential_evolution(
        lambda v: loss(simple_vector(*v), prepared), SIMPLE_BOUNDS,
        rng=seed, maxiter=maxiter, popsize=8, tol=1e-5, polish=True,
        x0=[32, 72.52], workers=1,
    )
    if not result.success or not np.isfinite(result.fun):
        raise ValueError(f"Simple Elo optimization failed: {result.message}")
    vector = simple_vector(*result.x)
    params = decode(vector)
    for games, arrays in zip(training_seasons, prepared):
        expected = [r['home_probability'] for r in replay(games, params, warmup_games=warmup)['predictions']]
        np.testing.assert_allclose(probabilities(vector, *arrays), expected, atol=1e-11, rtol=0)
    return params, {
        'model': 'simple Elo with fitted K and home advantage',
        'method': 'bounded differential evolution with L-BFGS-B polish',
        'seed': seed, 'maxiter': maxiter, 'popsize': 8, 'tolerance': 1e-5,
        'warmup_games_per_team': warmup,
        'bounds': {'k': SIMPLE_BOUNDS[0], 'home_advantage': SIMPLE_BOUNDS[1]},
        'parameters': asdict(params), 'training_log_loss': float(result.fun),
        'optimizer_success': bool(result.success), 'iterations': int(result.nit),
        'function_evaluations': int(result.nfev),
    }


def paired_comparison(full_rows, simple_rows, seed=42, resamples=10000):
    if resamples < 1:
        raise ValueError('At least one bootstrap resample is required')
    if len(full_rows) != len(simple_rows) or not full_rows:
        raise ValueError('Prediction sets must have equal nonzero lengths')
    daily = {}
    for full, simple in zip(full_rows, simple_rows):
        for key in ['game_id', 'start', 'home_win', 'eligible_for_evaluation']:
            if full[key] != simple[key]:
                raise ValueError(f'Unpaired predictions: {key}')
        if not full['eligible_for_evaluation']:
            continue
        y = full['home_win']
        p, q = np.clip([full['home_probability'], simple['home_probability']], 1e-12, 1-1e-12)
        ll = (-y*np.log(p)-(1-y)*np.log1p(-p))-(-y*np.log(q)-(1-y)*np.log1p(-q))
        bs = (p-y)**2-(q-y)**2
        acc = int((p >= .5) == y)-int((q >= .5) == y)
        key = str(slate_date(full))
        daily.setdefault(key, np.zeros(4))[:] += [ll, bs, acc, 1]
    if not daily:
        raise ValueError('No scored paired games')
    values = np.array(list(daily.values()))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(values), size=(resamples, len(values)))
    sampled = values[draws].sum(axis=1)
    differences = sampled[:, :3] / sampled[:, 3, None]
    observed = values.sum(axis=0)
    names = ['log_loss', 'brier_score', 'winner_accuracy']
    return {
        'direction': 'full model minus simple Elo; negative loss differences favor the full model',
        'games': int(observed[3]), 'slates': len(values), 'resamples': resamples, 'seed': seed,
        'method': 'paired bootstrap resampling whole Eastern-calendar daily slates',
        'limitation': 'Within-slate dependence preserved; dependence across days is not modeled. Intervals are exploratory.',
        'differences': {
            name: {'mean': float(observed[i]/observed[3]),
                   'interval_95': [float(x) for x in np.quantile(differences[:, i], [.025, .975])]}
            for i, name in enumerate(names)
        },
    }
