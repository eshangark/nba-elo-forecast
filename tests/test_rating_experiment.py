import copy
import math
import importlib.util
import unittest
from dataclasses import replace

HAS_RESEARCH = all(importlib.util.find_spec(p) is not None for p in ['numpy', 'scipy'])
if HAS_RESEARCH:
    from experiments.rating_quality import (LeadEngine, apply_heads, fit_heads,
                                            paired_intervals, replay_seasons)
from nba_forecast.model import Engine, Parameters
from nba_forecast.replay import replay
from test_model import game


@unittest.skipUnless(HAS_RESEARCH, 'Research dependencies are optional for live collection')
class RatingExperimentTests(unittest.TestCase):
    def test_original_matches_canonical_replay(self):
        games = [game(str(i), f'2024-10-{22+i}') for i in range(3)]
        expected = replay(games, Parameters(), warmup_games=10)['predictions']
        actual = replay_seasons({'2024-25': games}, Parameters())
        for a, b in zip(actual, expected):
            for key in ['home_rating', 'away_rating', 'home_probability', 'home_sos', 'forecast_cutoff']:
                self.assertEqual(a[key], b[key])

    def test_independent_update_preserves_sos_performance(self):
        p = Parameters(); rate = 35.; engine = LeadEngine(p, rate); g = game()
        # Include nonempty histories to exercise the actual performance factor.
        engine.team('A').performances = [.4]; engine.team('B').performances = [.7]
        prediction = engine.predict(g)
        reference = Engine(replace(p, k=p.k+rate*.5, lead_weight=0))
        reference.teams = copy.deepcopy(engine.teams)
        engine.update(g, prediction); reference.update(g, prediction)
        self.assertEqual(engine.teams, reference.teams)
        self.assertEqual(engine.params, p)

    def test_future_result_cannot_change_earlier_or_own_forecast(self):
        games = [game(str(i), f'2024-10-{22+i}') for i in range(3)]
        changed = copy.deepcopy(games); changed[1]['home']['points'] = 80
        for rate in [None, 35.]:
            a = replay_seasons({'2024-25': games}, Parameters(), rate)
            b = replay_seasons({'2024-25': changed}, Parameters(), rate)
            self.assertEqual([r['home_probability'] for r in a[:2]], [r['home_probability'] for r in b[:2]])
            self.assertNotEqual(a[2]['home_probability'], b[2]['home_probability'])

    def test_heads_reject_overlapping_training_and_evaluation(self):
        rows = replay_seasons({'2024-25': [game(str(i), f'2024-10-{22+i}') for i in range(4)]}, Parameters())
        heads = fit_heads(rows[:3])
        with self.assertRaises(ValueError):
            apply_heads(rows[1:], heads)
        scored = apply_heads(rows[3:], heads)
        self.assertTrue(math.isfinite(scored[0]['predicted_margin']))
        self.assertGreater(scored[0]['home_probability'], 0)

    def test_identical_forecasts_have_zero_paired_differences(self):
        rows = replay_seasons({'2024-25': [game(str(i), f'2024-10-{22+i}') for i in range(3)]}, Parameters())
        for r in rows:
            r['predicted_margin'] = 3.
        for score in paired_intervals(rows, rows, draws=20).values():
            self.assertEqual(score, {'difference': 0., 'lower_95': 0., 'upper_95': 0.})


if __name__ == '__main__':
    unittest.main()
