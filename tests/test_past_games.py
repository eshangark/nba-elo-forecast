import copy
import json
from pathlib import Path
import unittest

from nba_forecast.past_games import past_game_evidence
from nba_forecast.reliability import forecast_dependence, forecast_reliability, player_impact_evidence, team_calibration_evidence

ROOT=Path(__file__).resolve().parents[1]


class PastGameEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive=json.loads((ROOT/'data/seasons/2026-27/live.json').read_text())
        cls.row=next(r for r in cls.archive['result']['predictions'] if r['game_id']=='401909849')

    def recover(self,row=None,archive=None,result=None):
        archive=archive or self.archive
        return past_game_evidence(row or self.row,archive,result or archive['result'],ROOT/'data/seasons',ROOT)

    def test_pelicans_issued_probability_and_pregame_strength_are_preserved(self):
        original=copy.deepcopy(self.archive);result=self.recover()
        self.assertTrue(result['verified'])
        self.assertEqual(result['row']['away_probability'],self.row['away_probability'])
        strength=forecast_dependence(result['row'],result['archive']['result']['rankings'])
        self.assertEqual(strength['rank'],22);self.assertEqual(strength['opponent_rank'],28)
        self.assertAlmostEqual(strength['base_probability'],.5426114803326119)
        checks=forecast_reliability(result['row'],self.archive['result']['predictions'],result['completions'],None,self.row['issued_at'])
        self.assertEqual(checks['counts']['New Orleans Pelicans'],1)
        self.assertEqual(original,self.archive)

    def test_selected_and_future_results_do_not_change_pregame_context(self):
        changed=copy.deepcopy(self.archive)
        from nba_forecast.model import timestamp
        cutoff=timestamp(self.row['issued_at'])
        for game in changed['_internal']['games']:
            if timestamp(game['last_play_at'])>=cutoff:
                game['home']['points']+=100
        a=self.recover();b=self.recover(archive=changed)
        self.assertEqual(a['archive']['result']['rankings'],b['archive']['result']['rankings'])
        self.assertEqual(a['archive']['_internal']['feature_state'],b['archive']['_internal']['feature_state'])
        impacts=player_impact_evidence(a['row'],a['archive']['_internal'])
        self.assertTrue(impacts)
        self.assertTrue(any(p['History']=='Prior history available' for p in impacts))

    def test_reviewed_game_is_excluded_from_its_calibration(self):
        original={**self.row,'last_play_at':next(g['last_play_at'] for g in self.archive['_internal']['games'] if g['game_id']==self.row['game_id'])}
        result=team_calibration_evidence(self.row,[original],'New Orleans Pelicans',self.row['issued_at'],exact_model=True)
        self.assertEqual(result['games'],0)

    def test_rating_mismatch_does_not_use_current_rank_or_player_history(self):
        row=copy.deepcopy(self.row);row['away_rating']+=20
        result=self.recover(row=row)
        self.assertFalse(result['verified']);self.assertEqual(result['archive']['result']['rankings'],[])
        self.assertNotIn('feature_state',result['archive']['_internal'])
        self.assertIsNone(forecast_dependence(result['row'],[])['rank'])

    def test_missing_cutoff_remains_unavailable(self):
        row=copy.deepcopy(self.row);row.pop('issued_at');row.pop('forecast_cutoff')
        result=self.recover(row=row)
        self.assertFalse(result['verified']);self.assertNotIn('issued_at',result['row'])

    def test_historical_and_current_replays_recover_pre_cutoff_context(self):
        directory=ROOT/'data/seasons/2024-25'
        archive=json.loads((directory/'snapshot-v0.3.json').read_text())
        for name in ['snapshot-v0.3.json','current-model.json']:
            result=json.loads((directory/name).read_text())['result'];row=result['predictions'][30]
            recovered=self.recover(row=row,archive=archive,result=result)
            self.assertTrue(recovered['verified'],recovered['notes'])
            self.assertNotIn('issued_at',recovered['row'])
            self.assertEqual(recovered['row']['home_probability'],row['home_probability'])
            self.assertEqual(recovered['row']['kind'],row['kind'])
