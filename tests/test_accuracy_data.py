"""New tabs must reconcile exactly with stored results and Games' evidence."""
import copy
import hashlib
import json
import math
from pathlib import Path
import unittest

from nba_forecast.accuracy_data import (accuracy_catalog, evidence_before, favorite_calibration,
                                        season_scores, team_bands, team_scores, verified_rows)
from nba_forecast.dashboard_data import issued_rows
from nba_forecast.evaluation import favorite_bands
from nba_forecast.reliability import team_calibration_evidence
from nba_forecast.replay import metrics
from nba_forecast.seasons import load_index, load_season

ROOT = Path(__file__).resolve().parents[1]


class AccuracyDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries, cls.current = load_index(ROOT/'data/seasons')
        cls.archive = load_season(ROOT/'data/seasons', next(e for e in cls.entries if e['season'] == cls.current))
        cls.catalog, cls.notices = accuracy_catalog(ROOT, cls.entries, cls.archive)

    def test_chronological_scores_match_the_frozen_shared_sample(self):
        audit = json.loads((ROOT/'models/nba-v0.3/matched-evaluation.json').read_text())
        rows = self.catalog['chronological']
        self.assertEqual(len(rows), 3690)
        self.assertEqual({r['game_id'] for r in rows}, set(audit['pooled']['game_ids']))
        actual = metrics(rows); expected = audit['pooled']['metrics']['injury']
        for name in ['winner_accuracy', 'brier_score', 'log_loss']:
            self.assertAlmostEqual(actual[name], expected[name], places=12)
        self.assertEqual(sum(r['Games'] for r in season_scores(rows)), len(rows))

    def test_issued_scores_use_exactly_the_existing_methodology_rows(self):
        expected = issued_rows(self.archive)
        rows = [r for r in self.catalog['issued'] if r['season'] == self.current]
        self.assertEqual({r['game_id']: r['home_probability'] for r in rows},
                         {r['game_id']: r['home_probability'] for r in expected})
        for key in ['games', 'winner_accuracy', 'brier_score', 'log_loss']:
            self.assertEqual(metrics(rows)[key], metrics(expected)[key])

    def test_current_replay_matches_games_and_preserves_training_labels(self):
        for season in {r['season'] for r in self.catalog['replay']}:
            saved = json.loads((ROOT/'data/seasons'/season/'current-model.json').read_text())['result']
            rows = [r for r in self.catalog['replay'] if r['season'] == season]
            self.assertEqual({r['game_id']: (r['home_probability'], r['home_win']) for r in rows},
                             {r['game_id']: (r['home_probability'], r['home_win']) for r in saved['predictions']})
            self.assertEqual({r['evaluation_role'] for r in rows}, {saved.get('evaluation_role')})

    def test_team_counts_and_expected_wins_reconcile_without_double_scoring(self):
        for rows in self.catalog.values():
            teams = team_scores(rows)
            self.assertEqual(sum(t['Games'] for t in teams), 2*len(rows))
            self.assertEqual(sum(t['Actual wins'] for t in teams), len(rows))
            self.assertAlmostEqual(sum(t['Expected wins'] for t in teams), len(rows), places=9)
            for summary in teams:
                own = [r for r in rows if summary['Team'] in [r['home'], r['away']]]
                self.assertEqual(summary['Winner accuracy'], metrics(own)['winner_accuracy'])
                self.assertAlmostEqual(summary['Calibration gap (pp)'],
                                       (summary['Actual win rate']-summary['Mean forecast'])*100)

    def test_league_bands_match_games_favorite_bands(self):
        rows = self.catalog['chronological']; ours = favorite_calibration(rows)
        existing = favorite_bands(rows)
        self.assertEqual(sum(r['Games'] for r in ours), len(rows))
        for a, b in zip(ours, existing):
            self.assertEqual(a['Games'], b['games'])
            self.assertEqual(a['Mean forecast'], b['mean_forecast'])
            self.assertEqual(a['Actual win rate'], b['observed_win_rate'])
            self.assertEqual(a['Lower 95%'], b['lower_95'])

    def test_lookup_bands_match_games_at_identical_cutoff_and_fingerprint(self):
        row = self.archive['upcoming'][0]
        for source in ['chronological', 'issued']:
            eligible = evidence_before(self.catalog[source], row, source)
            for team in [row['home'], row['away']]:
                expected = team_calibration_evidence(row, self.catalog[source], team, row['issued_at'], exact_model=source == 'issued')
                actual = next(b for b in team_bands(eligible, team) if b['Probability range'] == expected['band'])
                self.assertEqual(actual['Games'], expected['games'])
                self.assertEqual(actual['Mean forecast'], expected['mean_forecast'])
                self.assertEqual(actual['Actual win rate'], expected['observed_win_rate'])
                self.assertEqual(actual['Observed-rate 95% interval'], expected['observed_rate_interval_95'])

    def test_band_boundaries_empty_bands_and_home_tie_policy(self):
        rows = []
        for i, p in enumerate([0., .2, .3, .5, .7, .8, 1.]):
            rows.append({'game_id': str(i), 'home': 'A', 'away': 'B', 'home_probability': p,
                         'away_probability': 1-p, 'home_win': int(p >= .5), 'kind': 'chronological_backtest',
                         'last_play_at': '2025-01-01T01:00Z', 'season': '2024-25'})
        bands = team_bands(rows, 'A')
        self.assertEqual(len(bands), 10)
        self.assertEqual([r['Games'] for r in bands], [1, 0, 1, 1, 0, 1, 0, 1, 1, 1])
        self.assertIsNone(bands[1]['Mean forecast'])
        self.assertEqual(metrics(rows)['winner_accuracy'], 1.)
        self.assertEqual(sum(r['Games'] for r in team_bands(rows, 'B')), len(rows))

    def test_integrity_rejects_outcomes_scores_missing_ids_duplicates_and_bad_cutoffs(self):
        row = copy.deepcopy(issued_rows(self.archive)[0])
        game = next(g for g in self.archive['_internal']['games'] if g['game_id'] == row['game_id'])
        for key, value in [('home_win', 1-row['home_win']), ('home', 'Wrong team'),
                           ('home_score', -1), ('home_probability', math.nan), ('issued_at', row['start'])]:
            bad = dict(row, **{key: value})
            with self.assertRaises(ValueError, msg=key):
                verified_rows([bad], [game], self.current, 'issued')
        with self.assertRaises(ValueError):
            verified_rows([row], [], self.current, 'issued')
        with self.assertRaises(ValueError):
            verified_rows([row, row], [game], self.current, 'issued')

    def test_schedule_corrections_preserve_both_times_without_rewriting_forecast(self):
        row = copy.deepcopy(issued_rows(self.archive)[0])
        game = copy.deepcopy(next(g for g in self.archive['_internal']['games'] if g['game_id'] == row['game_id']))
        from datetime import timedelta
        from nba_forecast.model import timestamp
        game['start'] = (timestamp(row['start'])+timedelta(minutes=5)).isoformat()
        recovered = verified_rows([row], [game], self.current, 'issued')[0]
        self.assertEqual(recovered['start'], row['start'])
        self.assertEqual(recovered['source_start'], game['start'])
        self.assertTrue(recovered['schedule_changed'])

    def test_catalog_and_summaries_leave_source_files_and_objects_unchanged(self):
        paths = [p for folder in ['models', 'data/seasons'] for p in (ROOT/folder).rglob('*') if p.is_file()]
        def hashes(): return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        before = hashes(); original = copy.deepcopy(self.archive)
        catalog, _ = accuracy_catalog(ROOT, self.entries, self.archive)
        for rows in catalog.values():
            season_scores(rows); team_scores(rows)
        self.assertEqual(self.archive, original)
        self.assertEqual(before, hashes())

    def test_stale_replays_are_excluded_and_missing_games_fail_closed(self):
        from tempfile import TemporaryDirectory
        from nba_forecast.live import digest
        from nba_forecast.forecasting import Forecaster
        row = copy.deepcopy(issued_rows(self.archive)[0])
        game = next(g for g in self.archive['_internal']['games'] if g['game_id'] == row['game_id'])
        archive = {'season': self.current, 'status': 'live', 'result': {'predictions': [row]},
                   '_internal': {'games': [game]}}
        bundle = json.loads((ROOT/'models/nba-v0.3/bundle.json').read_text())
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'models/nba-v0.3').mkdir(parents=True)
            (root/'models/nba-v0.3/bundle.json').write_text(json.dumps(bundle))
            path = root/'data/seasons'/self.current/'current-model.json'
            path.parent.mkdir(parents=True)
            candidate = {'source_result_sha256': 'stale', 'result': {
                'forecast_model_sha256': Forecaster(bundle).fingerprint, 'predictions': []}}
            path.write_text(json.dumps(candidate))
            entries = [{'season': self.current}]
            catalog, notices = accuracy_catalog(root, entries, archive)
            self.assertEqual(catalog['replay'], [])
            self.assertEqual(len(catalog['issued']), 1)
            self.assertTrue(any('stale' in n for n in notices))
            candidate['source_result_sha256'] = digest(archive['result'])
            path.write_text(json.dumps(candidate))
            with self.assertRaisesRegex(ValueError, 'game set differs'):
                accuracy_catalog(root, entries, archive)

    def test_cutoff_excludes_equal_later_and_other_model_results(self):
        forecast = {'issued_at': '2026-01-02T00:00Z', 'forecast_model_sha256': 'chosen'}
        prior = {'last_play_at': '2026-01-01T23:59Z', 'forecast_model_sha256': 'chosen'}
        rows = [prior, dict(prior, last_play_at=forecast['issued_at']),
                dict(prior, last_play_at='2026-01-03T00:00Z'), dict(prior, forecast_model_sha256='other')]
        self.assertEqual(evidence_before(rows, forecast, 'issued'), [prior])
        self.assertEqual(len(evidence_before(rows, forecast, 'chronological')), 2)
