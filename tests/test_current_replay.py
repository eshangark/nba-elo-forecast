"""Current-method replays preserve issued history and pregame availability."""
import copy
import unittest

from nba_forecast.current_replay import corrected_prediction, live_contexts, replay_live
from nba_forecast.forecasting import FeatureState, Forecaster, log_odds, ridge_probability
from nba_forecast.live import build_snapshot
from nba_forecast.model import Engine, Parameters
from test_forecasting import bundle
from test_live import ROSTER, SEASON, completed, scheduled


class CurrentReplayTests(unittest.TestCase):
    def fixture(self):
        predictor = Forecaster(bundle())
        initial = {'A': 1600., 'B': 1400.}
        seed = FeatureState(); seed.start_season(SEASON)
        old = build_snapshot(None, [], [scheduled()], Parameters(), ROSTER, '2026-10-19T20:00:00Z', SEASON)
        snapshot = build_snapshot(old, [completed()], [], Parameters(), ROSTER, '2026-10-21T02:00:00Z', SEASON,
                                  forecaster=predictor, initial_ratings=initial, feature_seed=seed.data)
        return snapshot, predictor

    def test_new_method_replays_old_games_without_rewriting_issued_forecasts(self):
        snapshot, predictor = self.fixture(); before = copy.deepcopy(snapshot)
        result = replay_live(snapshot, predictor)
        self.assertEqual(snapshot, before)
        self.assertNotEqual(result['predictions'][0]['home_probability'], snapshot['result']['predictions'][0]['home_probability'])
        self.assertEqual(result['rankings'], snapshot['result']['rankings'])
        self.assertEqual(result['metrics_all_issued']['games'], 1)
        self.assertEqual(result['metrics']['games'], 0)
        self.assertEqual(result['predictions'][0]['injury_status'], 'elo_fallback')

    def test_own_outcome_and_later_results_cannot_change_pregame_prediction(self):
        snapshot, predictor = self.fixture()
        expected = replay_live(snapshot, predictor)['predictions'][0]['home_probability']
        altered = copy.deepcopy(snapshot); altered['_internal']['games'][0]['home']['points'] += 5
        self.assertEqual(replay_live(altered, predictor)['predictions'][0]['home_probability'], expected)
        altered['_internal']['games'].append(completed('2', '2026-10-22'))
        self.assertEqual(replay_live(altered, predictor)['predictions'][0]['home_probability'], expected)

    def test_saved_injury_inputs_use_current_base_and_current_coefficients(self):
        snapshot, predictor = self.fixture(); game = completed(); base = Engine().predict(game)
        context = live_contexts(snapshot)['1']
        context.update(source={'published_at': '2026-10-19T19:00:00Z'}, injury_features=[-9.]+[0.]*18)
        row = corrected_prediction(game, base, FeatureState(), context, predictor)
        expected = ridge_probability(predictor.bundle['injury_head'], [log_odds(base['home_probability'])]+[0.]*18, base['home_probability'])
        self.assertEqual(row['home_probability'], expected)
        self.assertEqual(row['replay_input_basis'], 'saved_pregame_injury_covariates')
        for published in ['2026-10-19T21:00:00Z', '2026-10-18T01:00:00Z']:
            context['source']['published_at'] = published
            with self.assertRaises(ValueError):
                corrected_prediction(game, base, FeatureState(), context, predictor)

    def test_raw_injury_report_is_captured_for_future_replays(self):
        predictor = Forecaster(bundle()); report = {'1': {'A': {'submitted': True, 'players': []}}}
        source = {'published_at': '2026-10-19T19:00:00Z', 'sha256': 'fixture'}
        snapshot = build_snapshot(None, [], [scheduled()], Parameters(), ROSTER, '2026-10-19T20:00:00Z', SEASON,
                                  forecaster=predictor, initial_ratings={'A': 1500., 'B': 1500.}, injury_reports=report, injury_source=source)
        self.assertEqual(snapshot['upcoming'][0]['injury_report'], report['1'])
