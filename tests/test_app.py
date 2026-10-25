"""Optional UI integration checks; run with the Streamlit requirements installed."""

import importlib.util
import unittest
from pathlib import Path

HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None


@unittest.skipUnless(HAS_STREAMLIT, "Streamlit not installed")
class AppTests(unittest.TestCase):
    def test_only_published_probability_is_available(self):
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        from nba_forecast.live import build_snapshot
        from nba_forecast.model import Parameters
        from nba_forecast.forecasting import Forecaster
        from nba_forecast.seasons import current_season
        from test_forecasting import bundle
        from test_live import scheduled
        season = current_season()
        start_year = season[:4]
        pending = scheduled(); pending['season'] = int(start_year)+1
        pending['start'] = start_year+'-10-20T23:00:00Z'
        source = {'published_at': start_year+'-10-19T19:00:00Z', 'sha256': 'fixture'}
        payload = build_snapshot(None, [], [pending], Parameters(), {'A': 'Team A', 'B': 'Team B'},
                                 start_year+'-10-19T20:00:00Z', season, forecaster=Forecaster(bundle()),
                                 injury_reports={'1': {'A': {'submitted': True, 'players': []}}}, injury_source=source)
        with patch('nba_forecast.seasons.load_index', return_value=([{'season': season, 'file': 'unused'}], season)), \
             patch('nba_forecast.seasons.load_season', return_value=payload):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=20).run()
            self.assertFalse(app.exception)
            ratings = app.dataframe[0].value.copy()
            expected = payload['upcoming'][0]['probability_models']
            self.assertAlmostEqual(app.dataframe[1].value['Home win %'][0], expected['injury']['home_probability']*100)
            self.assertNotIn('Forecast model', [element.label for element in app.selectbox])
            for label in ['Elo rank · H / A','Prior final rank · H / A','Last 10 · H / A','Injury data','Input status','Team-strength context','Season evidence']:
                self.assertIn(label,app.dataframe[1].value.columns)
            self.assertTrue(any(tab.label == 'Information gaps' for tab in app.tabs))
            self.assertTrue(any('**Input status**' in m.value and 'Reports incomplete' in m.value for m in app.markdown))
            self.assertTrue(any('Player-availability scenario sensitivity is unavailable' in c.value for c in app.caption))
            self.assertTrue(any('Training replays are excluded' in c.value for c in app.caption))
            self.assertTrue(any('Team calibration · historical chronological forecasts' in m.value for m in app.markdown))
            self.assertFalse(any('moneyline' in str(f.value.columns).lower() for f in app.dataframe))
            self.assertTrue(any(tab.label == 'Original forecasts this season' for tab in app.tabs))
            self.assertTrue(any(tab.label == 'Historical chronological backtests' for tab in app.tabs))
            self.assertNotIn('Boosted comparison', '\n'.join(element.value for element in app.caption))
            # A stale session key from the removed selector cannot switch public forecasts.
            app.session_state[f'forecast_variant_{season}'] = {'value': 'boosted'}
            app.run()
            self.assertFalse(app.exception)
            self.assertAlmostEqual(app.dataframe[1].value['Home win %'][0], expected['injury']['home_probability']*100)
            self.assertTrue(ratings.equals(app.dataframe[0].value))

    def test_matchup_selection_updates_explanation_and_performance_samples(self):
        import json
        from streamlit.testing.v1 import AppTest
        from nba_forecast.seasons import current_season
        root=Path(__file__).resolve().parents[1]; season=current_season()
        original=json.loads((root/'data/seasons'/season/'live.json').read_text())
        if len(original['upcoming'])<2:
            self.skipTest('Two upcoming games required for this integration check')
        chosen=original['upcoming'][1]
        app=AppTest.from_file(str(root/'app.py'),default_timeout=20).run()
        app.session_state[f'matchup_details_{season}']={'value':chosen['game_id']}
        app.run(); self.assertFalse(app.exception)
        self.assertTrue(any(chosen['home'] in value.value and chosen['away'] in value.value for value in app.markdown))
        stages=[f.value for f in app.dataframe if 'Stage' in f.value.columns]
        self.assertGreaterEqual(len(stages),1)
        self.assertAlmostEqual(stages[0].iloc[-1]['Home win %'],chosen['home_probability']*100)
        historical = next(t for t in app.tabs if t.label == 'Historical chronological backtests')
        original_view = next(t for t in app.tabs if t.label == 'Original forecasts this season')
        issued=sum(r.get('kind')=='issued_live' and r.get('home_probability') is not None for r in original['result']['predictions'])
        self.assertEqual(next(int(m.value) for m in historical.metric if m.label == 'Games scored'),3690)
        self.assertEqual(next(int(m.value) for m in original_view.metric if m.label == 'Games scored'),issued)

    def test_past_matchup_selection_and_original_issued_basis(self):
        from streamlit.testing.v1 import AppTest
        root=Path(__file__).resolve().parents[1]
        app=AppTest.from_file(str(root/'app.py'),default_timeout=30).run()
        # New collector results can change the default date; select the fixture's date explicitly.
        app.session_state['game_date_2026-27']={'value':'2026-10-23'}
        app.session_state['past_matchup_2026-27_2026-10-23']={'value':'401909849'}
        app.session_state['past_basis_2026-27']={'value':'stored'}
        app.run();self.assertFalse(app.exception)
        self.assertTrue(any('New Orleans Pelicans: base Elo 54.3%' in m.value for m in app.markdown))
        self.assertTrue(any('New Orleans Pelicans is favored here and ranks #22' in m.value for m in app.markdown))
        self.assertTrue(any('Original issued forecast ·' in c.value for c in app.caption))
        app.session_state['past_basis_2026-27']={'value':'current'}
        app.run();self.assertFalse(app.exception)
        self.assertTrue(any('Current-method retrospective replay' in i.value for i in app.info))
        app.session_state['game_date_2026-27']={'value':'2026-10-22'}
        app.run();self.assertFalse(app.exception)

    def test_switching_seasons_updates_the_views(self):
        from streamlit.testing.v1 import AppTest
        from nba_forecast.seasons import current_season
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["selected_season"]["value"], current_season())
        app.session_state["selected_season"] = {"value": "2024-25"}
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 30)
        self.assertGreater(len(app.dataframe[1].value), 0)
        app.session_state["selected_season"] = {"value": current_season()}
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 30)
        self.assertTrue(any("No forecasts" in i.value or "No completed" in i.value for i in app.info) or any("Upcoming" in i.value for i in app.markdown))

    def test_live_past_games_render_with_and_without_issued_predictions(self):
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        from nba_forecast.live import build_snapshot
        from nba_forecast.model import Parameters
        from nba_forecast.seasons import current_season
        from test_model import game
        label = current_season()
        g = game('ui-final', label[:4]+'-10-20'); g['season'] = int(label[:4])+1
        pending = dict(g, event_state='pre')
        for side in ['home', 'away']:
            pending[side] = {k: g[side][k] for k in ['id', 'name']}
        pending.pop('last_play_at')
        roster = {'A': 'Team A', 'B': 'Team B'}
        initial = build_snapshot(None, [], [pending], Parameters(), roster, label[:4]+'-10-19T20:00:00Z', label)
        for previous in [None, initial]:
            live = build_snapshot(previous, [g], [], Parameters(), roster, label[:4]+'-10-21T02:00:00Z', label)
            with patch('nba_forecast.seasons.load_index', return_value=([{'season': label, 'file': 'unused'}], label)), \
                 patch('nba_forecast.seasons.load_season', return_value=live):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe[0].value), 2)
            self.assertEqual(len(app.dataframe[1].value), 1)
            self.assertIn("Prediction", app.dataframe[1].value.columns)
            self.assertNotIn("Coverage", app.dataframe[1].value.columns)
            self.assertEqual(app.dataframe[1].value["Prediction"][0], "Correct" if previous else "Unavailable")

    def test_matchup_lookup_reuses_games_forecast_and_calibration(self):
        import json
        from streamlit.testing.v1 import AppTest
        from nba_forecast.seasons import current_season
        root = Path(__file__).resolve().parents[1]; season = current_season()
        original = json.loads((root/'data/seasons'/season/'live.json').read_text())
        chosen = original['upcoming'][1]
        app = AppTest.from_file(str(root/'app.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue({'Teams', 'Games', 'Matchup', 'Accuracy', 'Methodology'}.issubset({t.label for t in app.tabs}))
        app.session_state[f'matchup_details_{season}'] = {'value': chosen['game_id']}
        app.selectbox(key=f'focused_matchup_{season}').select(chosen['game_id'])
        app.run(); self.assertFalse(app.exception)
        games = next(t for t in app.tabs if t.label == 'Games')
        matchup = next(t for t in app.tabs if t.label == 'Matchup')
        games_stages = next(f.value for f in games.dataframe if 'Stage' in f.value.columns)
        lookup_stages = next(f.value for f in matchup.dataframe if 'Stage' in f.value.columns)
        self.assertTrue(games_stages.equals(lookup_stages))
        self.assertAlmostEqual(lookup_stages.iloc[-1]['Home win %'], chosen['home_probability']*100)
        games_calibration = [f.value for f in games.dataframe if 'Probability range' in f.value.columns][:3]
        lookup_calibration = [f.value for f in matchup.dataframe if 'Probability range' in f.value.columns]
        self.assertEqual(len(lookup_calibration), 3)
        for old, new in zip(games_calibration, lookup_calibration):
            self.assertTrue(old.equals(new))

    def test_accuracy_source_season_team_and_replay_integrity(self):
        from streamlit.testing.v1 import AppTest
        from nba_forecast.seasons import current_season
        from nba_forecast.accuracy_data import accuracy_catalog, team_bands
        from nba_forecast.seasons import load_index
        root = Path(__file__).resolve().parents[1]; season = current_season()
        catalog, _ = accuracy_catalog(root, load_index(root/'data/seasons')[0])
        app = AppTest.from_file(str(root/'app.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        app.selectbox(key='accuracy_source_v2').select('chronological')
        app.run(); self.assertFalse(app.exception)
        app.selectbox(key='accuracy_team_chronological_All available seasons').select('New Orleans Pelicans')
        app.run(); self.assertFalse(app.exception)
        accuracy = next(t for t in app.tabs if t.label == 'Accuracy')
        bands = next(f.value for f in accuracy.dataframe if 'Probability range' in f.value.columns)
        expected = team_bands(catalog['chronological'], 'New Orleans Pelicans')
        self.assertEqual(bands['Games'].tolist(), [r['Games'] for r in expected])
        self.assertEqual(bands['Actual win rate'].fillna(-1).tolist(),
                         [r['Actual win rate'] if r['Actual win rate'] is not None else -1 for r in expected])
        app.selectbox(key='accuracy_source_v2').select('issued')
        app.run(); self.assertFalse(app.exception)
        accuracy = next(t for t in app.tabs if t.label == 'Accuracy')
        actual_count = next(int(m.value) for m in accuracy.metric if m.label == 'Evaluated games')
        self.assertEqual(actual_count, sum(r['season'] == season for r in catalog['issued']))
        app.selectbox(key='accuracy_source_v2').select('replay')
        app.run(); self.assertFalse(app.exception)
        app.selectbox(key='accuracy_season_replay').select('2024-25')
        app.run(); self.assertFalse(app.exception)
        accuracy = next(t for t in app.tabs if t.label == 'Accuracy')
        self.assertTrue(any('training-history games' in c.value for c in accuracy.caption))
        self.assertTrue(any('Probability range' in f.value.columns for f in accuracy.dataframe))
        self.assertTrue(any('Latest-model historical fit' in i.value for i in accuracy.info))
        app.session_state['selected_season'] = {'value': '2024-25'}
        app.run(); self.assertFalse(app.exception)
        matchup = next(t for t in app.tabs if t.label == 'Matchup')
        self.assertTrue(any('No upcoming forecasts' in i.value for i in matchup.info))

    def test_accuracy_defaults_to_latest_model_with_team_band_win_rates(self):
        import json
        from streamlit.testing.v1 import AppTest
        root = Path(__file__).resolve().parents[1]
        index = json.loads((root/'data/seasons/current-model-index.json').read_text())
        app = AppTest.from_file(str(root/'app.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='accuracy_source_v2').value, 'replay')
        self.assertEqual(app.selectbox(key='accuracy_season_replay').value, 'All available seasons')
        accuracy = next(t for t in app.tabs if t.label == 'Accuracy')
        self.assertEqual(next(int(m.value) for m in accuracy.metric if m.label == 'Evaluated games'), index['summary']['games'])
        app.selectbox(key='accuracy_team_replay_All available seasons').select('San Antonio Spurs')
        app.run(); self.assertFalse(app.exception)
        accuracy = next(t for t in app.tabs if t.label == 'Accuracy')
        bands = next(f.value for f in accuracy.dataframe if 'Probability range' in f.value.columns)
        expected = index['team_probability_bands']['San Antonio Spurs']
        self.assertEqual(bands['Games'].tolist(), [r['Games'] for r in expected])
        for column in ['Actual win rate', 'Mean forecast', 'Winner accuracy']:
            self.assertEqual(bands[column].fillna(-1).tolist(), [r[column] if r[column] is not None else -1 for r in expected])
