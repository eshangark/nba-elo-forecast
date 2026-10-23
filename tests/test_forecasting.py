"""Carryover, correction isolation, causal feature state and immutable issuance."""

import copy
from datetime import datetime
import importlib.util
import json
import math
import tempfile
from pathlib import Path
import unittest

from nba_forecast.forecasting import (FeatureState, Forecaster, INJURY_FEATURES, TEAM_FEATURES,
                                      carryover_ratings, ridge_probability, tree_probability)
from nba_forecast.live import build_snapshot, rebuild
from nba_forecast.model import Engine, Parameters
from test_live import completed, scheduled, ROSTER, SEASON
from test_model import game


def bundle():
    return {'version': '0.3.0', 'core_parameters': {}, 'carryover_fraction': .5,
            'feature_schema': {'injury': ['base_logit']+INJURY_FEATURES,
                               'boosted': ['base_logit']+TEAM_FEATURES+INJURY_FEATURES},
            'injury_head': {'means': [0.]*19, 'scales': [1.]*19, 'weights': [.4]+[0.]*19},
            'boosted_head': {'intercept': 0., 'blend': .5, 'trees': [[
                {'leaf': False, 'feature': 0, 'threshold': 0., 'left': 1, 'right': 2, 'value': 0.},
                {'leaf': True, 'value': -.5}, {'leaf': True, 'value': .5}]]}}


class ForecastingTests(unittest.TestCase):
    def test_carryover_is_centered_and_season_records_start_empty(self):
        initial = carryover_ratings({'A': 1600, 'B': 1400}, ROSTER)
        self.assertEqual(initial, {'A': 1550, 'B': 1450})
        engine, _ = rebuild([], Parameters(), ROSTER, datetime.fromisoformat('2026-10-19T20:00:00+00:00'), initial)
        self.assertEqual(engine.team('A').rating, 1550)
        self.assertEqual(engine.team('A').games, 0)
        with self.assertRaises(ValueError): carryover_ratings({'unknown': 1600}, ROSTER)

    def test_adjustment_never_changes_the_core_prediction_or_rating_update(self):
        g = completed()
        core = Engine(); base = core.predict(g); untouched = copy.deepcopy(base)
        state = FeatureState(); predictor = Forecaster(bundle())
        report = {'A': {'submitted': True, 'players': []}, 'B': {'submitted': False, 'players': []}}
        adjusted = predictor.predict(g, base, state, report, {'published_at': '2026-10-20T12:00:00Z', 'sha256': 'fixture'})
        self.assertGreater(adjusted['home_probability'], base['home_probability'])
        self.assertEqual(base, untouched)
        core.update(g, base)
        reference = Engine(); reference.update(g, reference.predict(g))
        self.assertEqual(core.team('A').rating, reference.team('A').rating)
        for model in adjusted['probability_models'].values():
            self.assertAlmostEqual(model['home_probability']+model['away_probability'], 1)

    def test_missing_game_report_falls_back_and_unsubmitted_is_explicit(self):
        g = scheduled(); base = Engine().predict(g); p = Forecaster(bundle()); state = FeatureState()
        fallback = p.predict(g, base, state)
        self.assertEqual(fallback['injury_status'], 'elo_fallback')
        self.assertEqual(fallback['home_probability'], base['home_probability'])
        self.assertTrue(all(v['home_probability'] == base['home_probability'] for v in fallback['probability_models'].values()))
        report = {'A': {'submitted': False, 'players': [{'athlete': 'p', 'status': 'Out'}]}}
        x, coverage = state.injury_features(g, report)
        self.assertEqual(coverage, ['not_submitted', 'unavailable'])
        self.assertEqual(x[0], 0)  # Unsubmitted rows cannot imply a known absence.

    def test_current_game_players_and_box_cannot_enter_own_features(self):
        state = FeatureState(); state.start_season(SEASON); g = completed()
        report = {'A': {'submitted': True, 'players': [{'athlete': 'p', 'status': 'Out'}]}}
        before = state.injury_features(g, report)
        base = Engine().predict(g); team_before = state.team_features(g, base)
        changed = copy.deepcopy(g); changed['home']['points'] += 20
        self.assertEqual(team_before, state.team_features(changed, base))
        self.assertEqual(before[0][0], 0)
        state.observe(g, base['home_probability'], {'A': [{'athlete': 'p', 'minutes': 30, 'game_score': 15}]})
        self.assertGreater(state.injury_features(g, report)[0][0], 0)
        with self.assertRaises(ValueError): state.observe(g, base['home_probability'])
        state.start_season('2027-28')
        self.assertEqual(state.data['last_rotation'], {})
        self.assertIn('p', state.data['player_history'])

    def test_rollout_preserves_old_revisions_and_new_models_score_same_game(self):
        now = '2026-10-19T20:00:00Z'
        old = build_snapshot(None, [], [scheduled()], Parameters(), ROSTER, now, SEASON)
        reports = {'1': {'A': {'submitted': True, 'players': []}}}
        kwargs = {'forecaster': Forecaster(bundle()), 'initial_ratings': {'A': 1550., 'B': 1450.},
                  'injury_reports': reports, 'injury_source': {'published_at': now, 'sha256': 'fixture'}}
        new = build_snapshot(old, [], [scheduled()], Parameters(), ROSTER, '2026-10-19T21:00:00Z', SEASON, **kwargs)
        self.assertEqual(new['_internal']['forecasts'][:1], old['_internal']['forecasts'])
        self.assertEqual(len(new['_internal']['forecasts']), 2)
        repeated = build_snapshot(new, [], [scheduled()], Parameters(), ROSTER, '2026-10-19T22:00:00Z', SEASON, **kwargs)
        self.assertEqual(repeated['_internal']['forecasts'], new['_internal']['forecasts'])
        final = build_snapshot(new, [completed()], [], Parameters(), ROSTER, '2026-10-21T02:00:00Z', SEASON, **kwargs)
        self.assertEqual(final['_internal']['forecasts'], new['_internal']['forecasts'])
        self.assertEqual({x['metrics_all_issued']['games'] for x in final['result']['model_comparison'].values()}, {1})
        base_engine, _ = rebuild([completed()], Parameters(), ROSTER, datetime.fromisoformat('2026-10-21T02:00:00+00:00'), kwargs['initial_ratings'])
        self.assertEqual(final['result']['rankings'][0]['elo'], base_engine.team('A').rating)

    def test_future_injury_publication_is_rejected_without_mutation(self):
        old = build_snapshot(None, [], [scheduled()], Parameters(), ROSTER, '2026-10-19T20:00:00Z', SEASON)
        saved = copy.deepcopy(old)
        with self.assertRaises(ValueError):
            build_snapshot(old, [], [scheduled()], Parameters(), ROSTER, '2026-10-19T21:00:00Z', SEASON,
                           injury_source={'published_at': '2026-10-19T22:00:00Z'})
        self.assertEqual(old, saved)

    def test_stale_input_falls_back_and_future_workload_uses_only_announced_games(self):
        stale = build_snapshot(None, [], [scheduled()], Parameters(), ROSTER, '2026-10-19T21:00:00Z', SEASON,
                               forecaster=Forecaster(bundle()), injury_reports={'1': {'A': {'submitted': True, 'players': []}}},
                               injury_source={'published_at': '2026-10-18T20:00:00Z'})
        self.assertEqual(stale['upcoming'][0]['injury_status'], 'elo_fallback')
        later = scheduled('2', '2026-10-21'); later['away'] = {'id': 'C', 'name': 'Team C'}
        roster = {**ROSTER, 'C': 'Team C'}
        result = build_snapshot(None, [], [scheduled(), later], Parameters(), roster, '2026-10-19T21:00:00Z', SEASON,
                                forecaster=Forecaster(bundle()), injury_reports={'2': {'A': {'submitted': True, 'players': []}}},
                                injury_source={'published_at': '2026-10-19T20:00:00Z'})
        self.assertEqual(result['upcoming'][1]['forecast_features']['boosted'][3], 1)  # one known game in prior four dates
        self.assertTrue(all(r['games'] == 0 for r in result['result']['rankings']))
        self.assertEqual(result['_internal']['feature_state']['observed_games'], [])

    def test_portable_tree_branches_and_ridge_logit_offset(self):
        model = bundle()['boosted_head']
        self.assertLess(tree_probability(model, [-1.], .5), .5)
        self.assertGreater(tree_probability(model, [1.], .5), .5)
        head = {'means': [2.], 'scales': [2.], 'weights': [0., 1.]}
        self.assertAlmostEqual(ridge_probability(head, [4.], .5), 1/(1+math.exp(-1)))
        with self.assertRaises(ValueError): ridge_probability(head, [], .5)

    def test_annual_transition_requires_a_complete_compatible_prior_season(self):
        from scripts.update_live import initialization
        root = Path(__file__).resolve().parents[1]
        archive = json.loads((root/'data/seasons/2025-26/snapshot.json').read_text())
        games = json.loads((root/'data/seasons/2025-26/games.json').read_text())
        model = bundle(); model['initialization'] = {'season': '2024-25'}
        predictor = Forecaster(model)
        state = FeatureState(); state.start_season('2025-26')
        archive['_internal'] = {'games': games, 'forecast_model_sha256': predictor.fingerprint, 'feature_state': state.data}
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)/'2025-26'; folder.mkdir()
            path = folder/'live.json'; path.write_text(json.dumps(archive))
            actual = initialization(predictor, None, Path(td), '2026-27')
            previous = archive['result']['rankings'][0]
            self.assertAlmostEqual(actual['ratings'][previous['team_id']], 1500+.5*(previous['elo']-1500))
            self.assertEqual(actual['features']['season'], '2026-27')
            archive['_internal']['games'][-1] = archive['_internal']['games'][0]
            path.write_text(json.dumps(archive))
            with self.assertRaises(ValueError): initialization(predictor, None, Path(td), '2026-27')

    @unittest.skipUnless(importlib.util.find_spec('sklearn') and importlib.util.find_spec('numba'), 'Scientific training dependencies not installed')
    def test_export_matches_sklearn_and_daily_player_cutoff(self):
        import numpy as np
        from sklearn.ensemble import HistGradientBoostingClassifier
        from nba_forecast.training import export_trees, prepare_history
        from unittest.mock import patch
        X = np.arange(200, dtype=float).reshape(-1, 1)
        model = HistGradientBoostingClassifier(max_iter=5, max_depth=2, min_samples_leaf=10,
                                               early_stopping=False, random_state=42).fit(X, X[:, 0] >= 100)
        portable = export_trees(model, 1.)
        np.testing.assert_allclose([tree_probability(portable, x, .5) for x in X], model.predict_proba(X)[:, 1], atol=1e-12, rtol=0)
        # Same-day trade/report overlap: an earlier tip must not update the morning forecast.
        a = game('early'); b = game('later'); b['start'] = '2024-10-23T01:00:00Z'; b['last_play_at'] = '2024-10-23T03:00:00Z'
        for side in ['home', 'away']: b[side]['id'] += '2'
        predictions = [Engine().predict(a), Engine().predict(b)]
        result = {'predictions': predictions}
        source = {'published_at': '2024-10-22T12:30:00Z', 'sha256': 'fixture', 'records': [
            {'game_date': '2024-10-22', 'matchup': '@', 'team': b['home']['name'], 'player': 'Player, Sample', 'status': 'Out'}]}
        aliases = {'sampleplayer': ['p']}
        players = {'early': {'A': [{'athlete': 'p', 'minutes': 40., 'game_score': 30.}]}}
        mapped = {'later': {'A2': {'submitted': True, 'players': [{'athlete': 'p', 'status': 'Out'}]}}}
        with patch('nba_forecast.training.rating_path', return_value={2025: result}), \
             patch('nba_forecast.training.join_report', return_value=mapped):
            rows, _, _, _ = prepare_history(Path('/nonexistent'), {2025: [a, b]}, players, aliases, {'2024-10-22': source})
        self.assertEqual(rows[1]['injury'][0], 0)
        self.assertEqual(rows[1]['injury'][10], 1)


if __name__ == '__main__':
    unittest.main()
