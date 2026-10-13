import copy
import unittest

from nba_forecast.model import Engine, Parameters, box_features, performance
from nba_forecast.replay import replay, metrics


def game(identifier="1", day="2024-10-22", neutral=False):
    def team(identifier, name, made, threes, points):
        return dict(id=identifier, name=name, points=points, fgm=made, fga=90,
                    threem=threes, threea=30, ftm=10, fta=12, oreb=10,
                    dreb=30, ast=20, stl=5, tov=10, largest_lead=20)
    return dict(game_id=identifier, start=day+"T23:00:00Z", season=2025,
                neutral=neutral, last_play_at=day+"T23:59:00Z",
                location=dict(latitude=42.36, longitude=-71.06, timezone="America/New_York"),
                home=team("A", "Team A", 40, 10, 100), away=team("B", "Team B", 35, 10, 90))


class ModelTests(unittest.TestCase):
    def test_neutral_symmetry_and_home_complement(self):
        engine = Engine()
        self.assertEqual(engine.predict(game(neutral=True))["home_probability"], 0.5)
        pred = engine.predict(game())
        self.assertGreater(pred["home_probability"], 0.5)
        self.assertAlmostEqual(pred["home_probability"] + pred["away_probability"], 1)

    def test_game_result_does_not_enter_forecast(self):
        original = game()
        changed = copy.deepcopy(original)
        changed["home"]["points"] = 180
        changed["home"]["largest_lead"] = 80
        self.assertEqual(Engine().predict(original), Engine().predict(changed))

    def test_negative_efficiency_is_preserved(self):
        g = game()
        self.assertLess(box_features(g["away"], g["home"])[0], 0)
        self.assertLess(performance(g["away"], g["home"]), performance(g["home"], g["away"]))

    def test_rebound_rates_use_opposite_category(self):
        g = game()
        g["away"]["dreb"] = 40
        self.assertAlmostEqual(box_features(g["home"], g["away"])[3], 10/50)

    def test_never_led_and_zero_turnovers_are_valid(self):
        engine = Engine()
        g = game()
        g["away"]["largest_lead"] = 0
        g["home"]["tov"] = 0
        engine.update(g, engine.predict(g))
        self.assertGreater(engine.team("A").rating, 1500)
        self.assertLess(engine.team("B").rating, 1500)

    def test_duplicate_game_rejected_without_second_update(self):
        engine = Engine()
        g = game()
        p = engine.predict(g)
        engine.update(g, p)
        rating = engine.team("A").rating
        with self.assertRaises(ValueError):
            engine.update(g, p)
        self.assertEqual(engine.team("A").rating, rating)

    def test_invalid_second_team_does_not_partially_update(self):
        engine = Engine()
        g = game()
        p = engine.predict(g)
        g["away"]["fga"] = 0
        with self.assertRaises(ValueError):
            engine.update(g, p)
        self.assertEqual(engine.team("A").rating, 1500)
        self.assertEqual(engine.team("A").games, 0)

    def test_back_to_back_rest_and_timezone(self):
        engine = Engine()
        g = game()
        engine.update(g, engine.predict(g))
        next_game = game("2", "2024-10-23")
        next_game["location"] = dict(latitude=34.05, longitude=-118.24, timezone="America/Los_Angeles")
        context = engine.context("A", next_game)
        self.assertEqual(context["rest"], 0)
        self.assertEqual(context["timezone_change"], -3)
        self.assertGreater(context["travel"], 4000)

    def test_replay_rejects_duplicates_and_multiple_seasons(self):
        with self.assertRaises(ValueError):
            replay([game(), game()])
        later = game("2", "2024-10-23")
        later["season"] = 2026
        with self.assertRaises(ValueError):
            replay([game(), later])

    def test_future_results_cannot_change_prior_prediction(self):
        first, second = game(), game("2", "2024-10-23")
        before = replay([second, first])["predictions"][0]
        second["home"], second["away"] = second["away"], second["home"]
        after = replay([first, second])["predictions"][0]
        self.assertEqual(before, after)

    def test_unavailable_results_cannot_enter_morning_forecast(self):
        first = game()
        first["last_play_at"] = "2024-10-23T16:00:00Z"
        with self.assertRaises(ValueError):
            replay([first, game("2", "2024-10-23")])

    def test_metrics_are_scored_against_outcomes(self):
        result = metrics([dict(home_probability=0.8, home_win=1), dict(home_probability=0.2, home_win=0)])
        self.assertAlmostEqual(result["brier_score"], 0.04)
        self.assertEqual(result["winner_accuracy"], 1)

    def test_params_reject_nan_and_sign_flipping_weight(self):
        for params in [dict(k=float("nan")), dict(performance_weight=1)]:
            with self.assertRaises(ValueError):
                Parameters(**params)


if __name__ == "__main__":
    unittest.main()
