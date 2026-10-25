"""Latest-model history is descriptive, version-bound and consistent across views."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nba_forecast.accuracy_data import accuracy_catalog, current_view_matches, evidence_before, team_bands
from nba_forecast.current_replay import refresh_current_replays
from nba_forecast.live import digest
from nba_forecast.reliability import team_calibration_evidence
from nba_forecast.seasons import load_index

ROOT = Path(__file__).resolve().parents[1]


class LatestModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries, cls.current = load_index(ROOT/'data/seasons')
        cls.index = json.loads((ROOT/'data/seasons/current-model-index.json').read_text())
        cls.catalog, _ = accuracy_catalog(ROOT, cls.entries)

    def test_persisted_inventory_covers_one_model_and_all_stored_games(self):
        rows = self.catalog['replay']
        self.assertEqual({r['forecast_model_sha256'] for r in rows}, {self.index['forecast_model_sha256']})
        self.assertEqual(len(rows), len({r['game_id'] for r in rows}))
        self.assertEqual(len(rows), self.index['summary']['games'])
        self.assertEqual(sum(s['games'] for s in self.index['seasons'].values()), len(rows))
        for season, item in self.index['seasons'].items():
            saved = json.loads((ROOT/'data/seasons'/item['file']).read_text())
            self.assertEqual(digest(saved['result']), item['result_sha256'])
            season_rows = [r for r in rows if r['season'] == season]
            for summary in [t for t in self.index['team_season_summary'] if t['Season'] == season]:
                own = [r for r in season_rows if summary['Team'] in [r['home'], r['away']]]
                expected = sum(r['home_probability'] if r['home'] == summary['Team'] else r['away_probability'] for r in own)
                wins = sum(r['home_win'] if r['home'] == summary['Team'] else 1-r['home_win'] for r in own)
                self.assertEqual(summary['Games'], len(own))
                self.assertAlmostEqual(summary['Expected wins'], expected)
                self.assertEqual(summary['Actual wins'], wins)

    def test_spurs_band_win_rate_and_winner_accuracy_have_distinct_meanings(self):
        rows = [{'game_id': str(i), 'home': 'Spurs', 'away': 'Rockets', 'home_probability': p,
                 'away_probability': 1-p, 'home_win': y, 'kind': 'current_method_replay',
                 'last_play_at': '2025-01-01T00:00Z', 'evaluation_role': 'training_replay'}
                for i, (p, y) in enumerate([(.7, 1), (.72, 0), (.78, 1), (.25, 1), (.28, 0), (.29, 0)])]
        before = copy.deepcopy(rows)
        bands = team_bands(rows, 'Spurs', allow_replay=True)
        favorite = next(r for r in bands if r['Probability range'] == '70–80%')
        underdog = next(r for r in bands if r['Probability range'] == '20–30%')
        self.assertEqual(favorite['Games'], 3)
        self.assertAlmostEqual(favorite['Mean forecast'], (.7+.72+.78)/3)
        self.assertAlmostEqual(favorite['Actual win rate'], 2/3)
        self.assertAlmostEqual(underdog['Actual win rate'], 1/3)
        self.assertAlmostEqual(underdog['Winner accuracy'], 2/3)
        self.assertEqual(rows, before)
        self.assertEqual(sum(b['Games'] for b in team_bands(rows, 'Spurs')), 0)

    def test_latest_matchup_and_accuracy_bands_agree_at_the_same_cutoff(self):
        archive = json.loads((ROOT/'data/seasons'/self.current/'live.json').read_text())
        forecast = archive['upcoming'][0]
        rows = evidence_before(self.catalog['replay'], forecast, 'replay')
        for team in [forecast['home'], forecast['away']]:
            game_view = team_calibration_evidence(forecast, self.catalog['replay'], team, forecast['issued_at'], allow_replay=True)
            lookup = next(r for r in team_bands(rows, team, allow_replay=True) if r['Probability range'] == game_view['band'])
            self.assertEqual(lookup['Games'], game_view['games'])
            self.assertEqual(lookup['Actual win rate'], game_view['observed_win_rate'])
            self.assertEqual(lookup['Mean forecast'], game_view['mean_forecast'])
            self.assertEqual(lookup['Winner accuracy'], game_view['winner_accuracy'])

    def test_corrupted_index_withholds_latest_analysis_but_keeps_issued_history(self):
        bad = copy.deepcopy(self.index); bad['forecast_model_sha256'] = 'old-model'
        original = Path.read_text
        def read(path, *args, **kwargs):
            return json.dumps(bad) if path.name == 'current-model-index.json' else original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            catalog, notes = accuracy_catalog(ROOT, self.entries)
        self.assertFalse(catalog['replay'])
        self.assertEqual(catalog['issued'], self.catalog['issued'])
        self.assertTrue(any('withheld' in n for n in notes))

    def test_games_rejects_indexed_forecasts_after_probability_or_model_drift(self):
        season = self.current
        archive = json.loads((ROOT/'data/seasons'/season/'live.json').read_text())
        candidate = json.loads((ROOT/'data/seasons'/season/'current-model.json').read_text())
        fingerprint = self.index['forecast_model_sha256']
        self.assertTrue(current_view_matches(archive, candidate, fingerprint, self.index))
        changed = copy.deepcopy(candidate); changed['result']['predictions'][0]['home_probability'] += .001
        self.assertFalse(current_view_matches(archive, changed, fingerprint, self.index))
        self.assertFalse(current_view_matches(archive, candidate, 'new-model', self.index))

    def test_model_refresh_updates_inventory_and_summaries_without_rewriting_issued_data(self):
        from test_current_replay import CurrentReplayTests
        snapshot, forecaster = CurrentReplayTests().fixture()
        with TemporaryDirectory() as temporary:
            root = Path(temporary); archives = root/'data/seasons'; season = snapshot['season']
            (root/'models/nba-v0.3').mkdir(parents=True); (archives/season).mkdir(parents=True)
            (root/'models/nba-v0.3/bundle.json').write_text(json.dumps(forecaster.bundle))
            (archives/'index.json').write_text(json.dumps({'seasons': [{'season': season, 'file': f'{season}/live.json'}]}))
            source = archives/season/'live.json'; source.write_text(json.dumps(snapshot)); original = source.read_bytes()
            refresh_current_replays(root)
            index = json.loads((archives/'current-model-index.json').read_text())
            self.assertEqual(index['forecast_model_sha256'], forecaster.fingerprint)
            self.assertEqual(index['summary']['games'], 1)
            self.assertEqual(source.read_bytes(), original)
            model = json.loads((root/'models/nba-v0.3/bundle.json').read_text())
            model['carryover_fraction'] = .4
            (root/'models/nba-v0.3/bundle.json').write_text(json.dumps(model))
            with self.assertRaisesRegex(ValueError, 'cover every completed season'):
                refresh_current_replays(root)
            self.assertEqual(source.read_bytes(), original)
