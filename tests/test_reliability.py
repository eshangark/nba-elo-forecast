"""Reliability labels must never turn missing data into confidence."""
import copy
import unittest

from nba_forecast.forecasting import INJURY_FEATURES
from nba_forecast.reliability import (injury_details, forecast_reliability,
                                      calibration_context, captured_adjustment)


def forecast():
    return {'game_id':'next', 'home':'A', 'away':'B', 'home_id':'a', 'away_id':'b',
            'start':'2026-10-25T23:00:00Z', 'issued_at':'2026-10-24T12:00:00Z',
            'home_probability':.62, 'base_home_probability':.6,
            'injury_status':'complete', 'forecast_model_sha256':'current',
            'injury_source':{'published_at':'2026-10-24T11:00:00Z'},
            'injury_report':{'a':{'submitted':True, 'players':[]}, 'b':{'submitted':True, 'players':[]}},
            'forecast_features':{'injury':[.4]+[0.]*len(INJURY_FEATURES)}}


class ReliabilityTests(unittest.TestCase):
    def test_submission_does_not_hide_missing_players_or_histories(self):
        row=forecast()
        row['forecast_features']['injury'][1+INJURY_FEATURES.index('home_no_history')]=2
        self.assertEqual(injury_details(row)['label'], 'Player data gaps')
        self.assertEqual(injury_details(row)['teams'][0]['Missing histories'], 2)
        row=forecast();row['injury_report']['a']['players']=[{'name':'Unmatched', 'athlete':None, 'status':'Out'}]
        self.assertEqual(injury_details(row)['label'], 'Player data gaps')
        self.assertIn('Unmatched',injury_details(row)['teams'][0]['Unmatched players'])

    def test_unknown_coverage_is_never_complete(self):
        row=forecast();row['forecast_features']=None
        self.assertEqual(injury_details(row)['label'], 'Player coverage unverified')
        self.assertIsNone(injury_details(row)['teams'][0]['Missing histories'])
        row=forecast();row['injury_report'].pop('b')
        self.assertEqual(injury_details(row)['label'], 'Reports incomplete')
        row['injury_status']='elo_fallback'
        self.assertEqual(injury_details(row)['label'], 'No usable report · base Elo')

    def test_unresolved_status_and_complete_inputs_are_distinct(self):
        row=forecast();self.assertEqual(injury_details(row)['label'], 'Captured inputs complete')
        row['injury_report']['a']['players']=[{'name':'Player Q','athlete':'q','status':'Questionable'}]
        self.assertEqual(injury_details(row)['label'], 'Availability unresolved')
        self.assertEqual(injury_details(row)['teams'][0]['Unresolved availability'], 'Player Q')

    def test_fresh_snapshot_can_contain_an_older_unchanged_forecast(self):
        check=forecast_reliability(forecast(), [], {}, '2026-10-24T19:00:00Z','2026-10-24T20:00:00Z')
        self.assertEqual(check['freshness'], 'Snapshot checked within 2h')
        self.assertEqual(check['snapshot_age'],'1h 0m ago')
        self.assertEqual(check['forecast_age'],'8h 0m ago')
        check=forecast_reliability(forecast(), [], {}, '2026-10-24T17:00:00Z','2026-10-24T20:00:00Z')
        self.assertEqual(check['freshness'], 'Snapshot older than 2h')
        check=forecast_reliability(forecast(), [], {}, '2026-10-24T21:00:00Z','2026-10-24T20:00:00Z')
        self.assertEqual(check['snapshot_age'],'Unknown')

    def test_maturity_uses_completion_before_issuance_not_current_rankings(self):
        rows=[{'game_id':'one','home':'A','away':'B'}, {'game_id':'later','home':'A','away':'B'}]
        check=forecast_reliability(forecast(), rows, {'one':'2026-10-23T23:00:00Z','later':'2026-10-24T13:00:00Z'},
                                   '2026-10-24T19:00:00Z','2026-10-24T20:00:00Z')
        self.assertEqual(check['counts'],{'A':1,'B':1})
        self.assertEqual(check['maturity'],'Limited season evidence')
        check=forecast_reliability(forecast(), rows, {}, None,'2026-10-24T20:00:00Z')
        self.assertEqual(check['maturity'],'Season evidence unknown')

    def test_stale_report_and_past_tipoff_are_visible(self):
        check=forecast_reliability(forecast(), [], {}, '2026-10-26T00:00:00Z','2026-10-26T01:00:00Z')
        self.assertTrue(check['report_outdated'])
        self.assertEqual(check['freshness'],'Tip-off passed · pregame snapshot')

    def test_live_calibration_excludes_later_results_other_models_and_training(self):
        row=forecast()
        past={'home_probability':.61,'home_win':1,'kind':'issued_live',
              'last_play_at':'2026-10-23T23:00:00Z','forecast_model_sha256':'current'}
        evidence=[past,dict(past,kind='current_method_replay'),dict(past,forecast_model_sha256='old'),
                  dict(past,last_play_at='2026-10-24T13:00:00Z'),dict(past,last_play_at=None)]
        result=calibration_context(row,evidence,before=row['issued_at'],exact_model=True)
        self.assertEqual(result['games'],1)
        self.assertEqual(result['band'],'60–65%')
        self.assertIsNone(calibration_context(row,[dict(past,kind='training_replay')]))
        self.assertIsNone(calibration_context(row,[dict(past,home_probability=.7)]))

    def test_away_favorite_and_boundary_use_same_favorite_bands(self):
        row=forecast();row['home_probability']=.35
        band=calibration_context(row,[{'kind':'chronological_backtest','home_probability':.35,'home_win':0}])
        self.assertEqual(band['band'],'65–70%');self.assertEqual(band['wins'],1)

    def test_checks_do_not_modify_forecasts_or_probability(self):
        row=forecast();before=copy.deepcopy(row)
        forecast_reliability(row, [], {}, '2026-10-24T19:00:00Z','2026-10-24T20:00:00Z')
        self.assertAlmostEqual(captured_adjustment(row),2.)
        self.assertEqual(before,row)
        self.assertIsNone(captured_adjustment({'home_probability':.5}))


class TeamEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.row=forecast();self.row['away_probability']=1-self.row['home_probability']
        self.row.update(home_rating=1400.,away_rating=1350.)
        self.evidence=[{'game_id':str(i),'kind':'chronological_backtest','home':'A' if i<4 else 'C','away':'B',
                        'home_probability':.62,'home_win':int(i<4),
                        'last_play_at':'2026-10-23T23:00:00Z'} for i in range(8)]

    def test_team_residual_pooling_and_no_team_fallback(self):
        from nba_forecast.reliability import team_calibration_evidence
        result=team_calibration_evidence(self.row,self.evidence,'A',self.row['issued_at'])
        self.assertEqual(result['games'],4);self.assertEqual(result['sample_label'],'Small sample')
        self.assertAlmostEqual(result['raw_error_pp'],38)
        self.assertLess(abs(result['pooled_error_pp']+12),abs(result['raw_error_pp']+12))
        self.assertEqual(result['band'],'60–70%')
        empty=team_calibration_evidence(self.row,[],'A',self.row['issued_at'])
        self.assertIsNone(empty['raw_error_pp']);self.assertIsNone(empty['pooled_error_pp'])

    def test_team_evidence_rejects_later_results_replays_and_wrong_bundle(self):
        from nba_forecast.reliability import team_calibration_evidence
        evidence=[dict(self.evidence[0],kind='issued_live',forecast_model_sha256='current')]
        bad=[dict(evidence[0],game_id='later',last_play_at='2026-10-24T13:00:00Z'),
             dict(evidence[0],game_id='replay',kind='current_method_replay'),
             dict(evidence[0],game_id='wrong',forecast_model_sha256='older')]
        result=team_calibration_evidence(self.row,evidence+bad,'A',self.row['issued_at'],exact_model=True)
        self.assertEqual(result['games'],1)
        with self.assertRaises(ValueError):
            team_calibration_evidence(self.row,evidence*2,'A',self.row['issued_at'],exact_model=True)

    def test_strength_context_does_not_use_later_rankings(self):
        from nba_forecast.reliability import forecast_dependence
        ranks=[{'team':'C','elo':1600},{'team':'D','elo':1500},{'team':'A','elo':1400},{'team':'B','elo':1350}]
        original=copy.deepcopy(self.row);strength=forecast_dependence(self.row,ranks)
        self.assertEqual(strength['strength_label'],'Low-rated favorite');self.assertEqual(strength['rank'],3)
        self.assertAlmostEqual(strength['adjustment_pp'],2.)
        ranks[2]['elo']=1450
        self.assertIsNone(forecast_dependence(self.row,ranks)['rank'])
        self.assertEqual(original,self.row)

    def test_player_coverage_cannot_substitute_later_histories(self):
        from nba_forecast.reliability import player_impact_evidence
        self.row['state_sha256']='old';self.row['injury_report']['a']['players']=[{'name':'Player','athlete':'p','status':'Out'}]
        internal={'state_sha256':'new','feature_state':{'player_history':{'p':[350.,10.,200.]}}}
        self.assertIsNone(player_impact_evidence(self.row,internal)[0]['Expected minutes'])
        internal['state_sha256']='old';result=player_impact_evidence(self.row,internal)[0]
        self.assertEqual(result['Expected minutes'],35.)
        self.assertAlmostEqual(result['Prior contribution proxy'],35*224/430)
