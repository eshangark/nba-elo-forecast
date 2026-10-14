"""Optional UI integration checks; run with the Streamlit requirements installed."""

import importlib.util
import unittest
from pathlib import Path

HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None


@unittest.skipUnless(HAS_STREAMLIT, "Streamlit not installed")
class AppTests(unittest.TestCase):
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
