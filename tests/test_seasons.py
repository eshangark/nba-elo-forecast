import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from nba_forecast.seasons import current_season, load_index, load_season


class SeasonTests(unittest.TestCase):
    def test_season_labels_span_calendar_years(self):
        self.assertEqual(current_season(date(2026, 10, 12)), "2026-27")
        self.assertEqual(current_season(date(2027, 2, 1)), "2026-27")
        self.assertEqual(current_season(date(2026, 6, 20)), "2025-26")

    def test_current_season_is_available_even_without_a_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.json").write_text(json.dumps({"seasons": [{"season": "2024-25", "file": None}]}))
            entries, selected = load_index(root, date(2026, 10, 12))
            self.assertEqual(selected, "2026-27")
            self.assertEqual(entries[0]["season"], selected)
            self.assertIsNone(load_season(root, entries[0]))

    def test_archive_cannot_point_to_another_season(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "snapshot.json").write_text(json.dumps({"season": "2023-24"}))
            with self.assertRaises(ValueError):
                load_season(root, {"season": "2024-25", "file": "snapshot.json"})

    def test_archive_path_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                load_season(folder, {"season": "2024-25", "file": "../snapshot.json"})
