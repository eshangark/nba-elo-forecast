"""Meaningful checks of the comparator's independence and paired scoring."""

import copy
import importlib.util
import unittest

HAS_FITTING = all(importlib.util.find_spec(p) is not None for p in ['scipy', 'numba'])


@unittest.skipUnless(HAS_FITTING, 'Fitting dependencies not installed')
class BenchmarkTests(unittest.TestCase):
    def test_simple_elo_ignores_box_score_and_travel_when_outcomes_are_unchanged(self):
        from nba_forecast.benchmark import simple_vector
        from nba_forecast.fitting import decode
        from nba_forecast.replay import replay
        from test_model import game
        games = [game(str(i), f'2024-10-{22+i:02d}') for i in range(4)]
        altered = copy.deepcopy(games)
        for g in altered:
            g['home'].update(fgm=50, points=120, largest_lead=50, oreb=20, dreb=45)
            g['away'].update(largest_lead=0, ast=10, tov=15)
            g['location'] = dict(latitude=34.05, longitude=-118.24, timezone='America/Los_Angeles')
        params = decode(simple_vector(30, 50))
        original = replay(games, params)
        changed = replay(altered, params)
        self.assertEqual([r['home_probability'] for r in original['predictions']],
                         [r['home_probability'] for r in changed['predictions']])
        # A standard Elo update is zero-sum and independent of final margin.
        for row in original['predictions']:
            delta = params.k*(row['home_win']-row['home_probability'])
            self.assertAlmostEqual(row['home_rating_change'], delta)
            self.assertAlmostEqual(row['away_rating_change'], -delta)

    def test_paired_bootstrap_preserves_identity_and_zero_difference(self):
        from nba_forecast.benchmark import paired_comparison
        from nba_forecast.replay import replay
        from test_model import game
        rows = replay([game('1'), game('2', '2024-10-23')])['predictions']
        result = paired_comparison(rows, rows, resamples=100)
        self.assertEqual(result['games'], 2)
        self.assertEqual(result['slates'], 2)
        for metric in result['differences'].values():
            self.assertEqual(metric, {'mean': 0.0, 'interval_95': [0.0, 0.0]})
        mismatched = copy.deepcopy(rows)
        mismatched[0]['game_id'] = 'wrong'
        with self.assertRaises(ValueError):
            paired_comparison(rows, mismatched)

    def test_better_forecasts_have_negative_loss_differences(self):
        from nba_forecast.benchmark import paired_comparison
        from nba_forecast.replay import replay
        from test_model import game
        full = replay([game('1')])['predictions']
        simple = copy.deepcopy(full)
        full[0]['home_probability'] = .8
        simple[0]['home_probability'] = .5
        difference = paired_comparison(full, simple, resamples=100)['differences']
        self.assertLess(difference['log_loss']['mean'], 0)
        self.assertLess(difference['brier_score']['mean'], 0)

    def test_saved_comparison_matches_frozen_release_and_source_records(self):
        import csv
        import hashlib
        import json
        from pathlib import Path
        from nba_forecast.model import Parameters
        from nba_forecast.replay import replay
        root = Path(__file__).resolve().parents[1]
        report = json.loads((root / 'models/comparison-v0.2/results.json').read_text())
        release = Parameters(**json.loads((root / 'models/nba-v0.2/parameters.json').read_text()))
        simple = Parameters(**json.loads((root / 'models/comparison-v0.2/fit_2025.json').read_text())['simple_elo']['parameters'])
        with (root / 'models/comparison-v0.2/predictions.csv').open() as f:
            predictions = list(csv.DictReader(f))
        for fold in report['folds']:
            self.assertTrue(all(label < fold['evaluation_season'] for label in fold['training_seasons']))
        for fold in report['frozen_release_comparison']:
            season = fold['evaluation_season']
            raw = (root / f'data/seasons/{season}/games.json').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), report['source_file_sha256'][season])
            games = json.loads(raw)
            a = replay(games, release, fitted=True, warmup_games=10)
            b = replay(games, simple, fitted=True, warmup_games=10)
            self.assertEqual(a['metrics'], fold['full_metrics'])
            self.assertEqual(b['metrics'], fold['simple_metrics'])
            rows = [r for r in predictions if r['protocol'] == 'original_frozen_release' and r['season'] == season]
            self.assertEqual(len(rows), 1230)
            for row, full, baseline in zip(rows, a['predictions'], b['predictions']):
                self.assertEqual(row['game_id'], full['game_id'])
                self.assertEqual(float(row['full_probability']), full['home_probability'])
                self.assertEqual(float(row['simple_probability']), baseline['home_probability'])
