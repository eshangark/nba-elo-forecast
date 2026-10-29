import copy
from dataclasses import asdict
import unittest

from nba_forecast.dashboard_data import elo_ranks, recent_record, probability_steps, data_gaps, issued_rows, team_game_history
from nba_forecast.forecasting import Forecaster,FeatureState
from nba_forecast.model import Engine,Parameters
from test_forecasting import bundle
from test_model import game


class DashboardDataTests(unittest.TestCase):
    def test_team_game_history_uses_team_perspective_and_eastern_dates(self):
        home = dict(game_id='1', start='2026-10-23T00:30:00Z', home='A', away='B',
                    home_win=1, home_score=110, away_score=100,
                    home_rating_after=1510, home_rating_change=10,
                    away_rating_after=1490, away_rating_change=-10)
        away = dict(home, game_id='2', start='2026-10-25T00:30:00Z', home='B', away='A')
        unrelated = dict(home, game_id='3', home='C', away='D')
        incomplete = dict(home, game_id='4', home_score=None)
        rows = [home, unrelated, away, incomplete]
        history = team_game_history('A', rows)
        self.assertEqual(len(history), 2)
        self.assertEqual(str(history[0]['Date']), '2026-10-24')
        self.assertEqual(history[0]['Opponent'], 'B')
        self.assertEqual(history[0]['Home / Away'], 'Away')
        self.assertEqual(history[0]['Result'], 'L')
        self.assertEqual(history[0]['Score'], '100–110')
        self.assertEqual(history[0]['Elo after'], 1490)
        self.assertEqual(history[0]['Elo change'], -10)
        self.assertEqual(history[1]['Home / Away'], 'Home')
        self.assertEqual(history[1]['Result'], 'W')
        self.assertEqual(history[1]['Score'], '110–100')
        self.assertEqual(team_game_history('Unknown', rows), [])
        self.assertEqual(team_game_history('A', []), [])

    def test_rank_ties_and_recent_form_exclude_incomplete_or_future_games(self):
        self.assertEqual(elo_ranks([{'team':'A','elo':1600},{'team':'B','elo':1600},{'team':'C','elo':1500}]),{'A':1,'B':1,'C':3})
        rows=[dict(game_id=str(i),home='A',away='B',home_win=i%2,start=f'2026-10-{i+1:02}T12:00:00Z') for i in range(12)]
        record=recent_record('A',rows,'2026-10-13T00:00:00Z',{'11':'2026-10-13T01:00:00Z'})
        self.assertEqual(record['games'],10);self.assertEqual(record['wins'],5)
        self.assertEqual(recent_record('C',rows,'2026-10-13T00:00:00Z')['games'],0)

    def test_breakdown_reconstructs_home_and_neutral_forecasts_exactly(self):
        parameters=Parameters()
        for neutral in [False,True]:
            g=game(neutral=neutral);base=Engine(parameters).predict(g)
            prediction={**base,**Forecaster(bundle()).predict(g,base,FeatureState(),{'A':{'submitted':True,'players':[]}}, {'published_at':'2024-10-22T12:00:00Z'})}
            steps=probability_steps(prediction,asdict(parameters))
            self.assertEqual(len(steps),4)
            self.assertAlmostEqual(steps[-1]['Home win %'],prediction['home_probability']*100)
            self.assertAlmostEqual(sum(s['Change (pp)'] or 0 for s in steps),steps[-1]['Home win %']-steps[0]['Home win %'])
            if neutral:self.assertAlmostEqual(steps[1]['Change (pp)'],0)
            bad=copy.deepcopy(prediction);bad['base_home_probability']=.99
            self.assertEqual(probability_steps(bad,asdict(parameters)),[])

    def test_data_gaps_describe_early_season_and_no_report_without_confidence_grade(self):
        row={'home':'A','away':'B','injury_status':'elo_fallback'}
        messages=data_gaps(row,[{'team':'A','games':2},{'team':'B','games':15}])
        self.assertTrue(any('only 2' in x for x in messages))
        self.assertTrue(any('Missing reports' in x for x in messages))
        self.assertFalse(any('only 15' in x for x in messages))

    def test_original_issued_scores_exclude_replays_and_unforecasted_games(self):
        rows=[dict(kind='issued_live',home_probability=.6),dict(kind='current_method_replay',home_probability=.7),dict(kind='unforecasted_backfill',home_probability=None)]
        self.assertEqual(issued_rows({'result':{'predictions':rows}}),rows[:1])
