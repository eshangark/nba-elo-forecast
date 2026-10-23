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
            self.assertNotIn('Boosted comparison', '\n'.join(element.value for element in app.caption))
            # A stale session key from the removed selector cannot switch public forecasts.
            app.session_state[f'forecast_variant_{season}'] = {'value': 'boosted'}
            app.run()
            self.assertFalse(app.exception)
            self.assertAlmostEqual(app.dataframe[1].value['Home win %'][0], expected['injury']['home_probability']*100)
            self.assertTrue(ratings.equals(app.dataframe[0].value))

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
