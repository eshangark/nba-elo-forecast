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
        self.assertEqual(app.selectbox(key="selected_season").value, current_season())
        app.selectbox(key="selected_season").select("2024-25").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 30)
        self.assertGreater(len(app.dataframe[1].value), 0)
        app.selectbox(key="selected_season").select(current_season()).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 30)
        self.assertTrue(any("No forecasts" in i.value for i in app.info))
