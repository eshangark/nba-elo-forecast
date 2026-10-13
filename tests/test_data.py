import json
import unittest
from pathlib import Path

from nba_forecast.data import parse_summary


class FixedCity:
    def resolve(self, address):
        return {"id": "test-city", "latitude": 0, "longitude": 0, "timezone": "America/New_York"}


class DataTests(unittest.TestCase):
    def fixture(self, identifier):
        return json.loads((Path(__file__).parent / "fixtures" / f"{identifier}.json").read_text())

    def test_missing_largest_lead_uses_validated_score_path(self):
        game = parse_summary(self.fixture("401704635"), FixedCity())
        self.assertEqual(game["home"]["largest_lead"], 16)
        self.assertEqual(game["away"]["largest_lead"], 7)
        self.assertEqual(len(game["quality_actions"]), 2)

    def test_recovery_rejects_inconsistent_final_play_score(self):
        payload = self.fixture("401704635")
        final_play = max(payload["plays"], key=lambda p: int(p["sequenceNumber"]))
        final_play["homeScore"] = 0
        with self.assertRaises(ValueError):
            parse_summary(payload, FixedCity())

    def test_contradictory_aggregate_uses_complete_player_rows(self):
        game = parse_summary(self.fixture("401704652"), FixedCity())
        self.assertEqual(game["home"]["fgm"], 37)
        self.assertEqual(game["home"]["points"], 103)
        self.assertEqual(game["away"]["fgm"], 36)
        self.assertEqual(game["away"]["points"], 105)
        self.assertEqual(len(game["quality_actions"]), 2)

    def test_missing_active_player_stats_cannot_repair_a_box_score(self):
        payload = self.fixture("401704652")
        athlete = payload["boxscore"]["players"][0]["statistics"][0]["athletes"][0]
        athlete["stats"] = []
        athlete["didNotPlay"] = False
        with self.assertRaises(ValueError):
            parse_summary(payload, FixedCity())

    def test_in_progress_game_is_not_accepted_as_final(self):
        payload = self.fixture("401704635")
        payload["header"]["competitions"][0]["status"]["type"]["completed"] = False
        with self.assertRaises(ValueError):
            parse_summary(payload, FixedCity())
