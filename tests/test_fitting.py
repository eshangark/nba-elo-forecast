import importlib.util
import unittest

HAS_FITTING = all(importlib.util.find_spec(p) is not None for p in ["scipy", "numba"])


@unittest.skipUnless(HAS_FITTING, "Fitting dependencies not installed")
class FittingTests(unittest.TestCase):
    def test_accelerated_replay_matches_parameter_dependent_canonical_replay(self):
        import numpy as np
        from nba_forecast.fitting import prepare, probabilities, initial_vector, decode
        from nba_forecast.replay import replay
        from test_model import game
        games=[game(str(i), f"2024-10-{22+i:02d}") for i in range(5)]
        games[2]["home"],games[2]["away"]=games[2]["away"],games[2]["home"]
        prepared=prepare(games,warmup=0)
        for shift in [0,0.2]:
            vector=initial_vector()
            vector[0]=20+shift
            vector[1]=80
            vector[6]=0.3
            vector[7:]+=shift
            expected=[r["home_probability"] for r in replay(games,decode(vector))["predictions"]]
            np.testing.assert_allclose(probabilities(vector,*prepared),expected,atol=1e-12,rtol=0)

    def test_weight_parameterization_is_normalized_and_positive(self):
        from nba_forecast.fitting import decode, initial_vector
        params=decode(initial_vector())
        self.assertAlmostEqual(sum(params.alpha_weights),1)
        self.assertGreater(min(params.alpha_weights),0)

    def test_scoring_warmup_is_past_only(self):
        from nba_forecast.replay import replay
        from test_model import game
        result=replay([game("1"),game("2","2024-10-23")],warmup_games=1)
        self.assertFalse(result["predictions"][0]["eligible_for_evaluation"])
        self.assertTrue(result["predictions"][1]["eligible_for_evaluation"])
        self.assertEqual(result["metrics"]["games"],1)
