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
        game_counts=[int(m.value) for m in app.metric if m.label=='Games scored']
        issued=sum(r.get('kind')=='issued_live' and r.get('home_probability') is not None for r in original['result']['predictions'])
        self.assertEqual(game_counts[0],3690)
        self.assertEqual(game_counts[1],issued)

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
