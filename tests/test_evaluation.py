import copy
import unittest

from nba_forecast.evaluation import compare_samples, compare_variants, favorite_bands


def row(identifier='1',p=.6,eligible=True):
    return dict(game_id=identifier,start='2026-10-20T23:00:00Z',forecast_cutoff='2026-10-20T12:00:00Z',
                home='A',away='B',home_win=1,eligible_for_evaluation=eligible,
                home_probability=p,away_probability=1-p,kind='historical_replay')


class EvaluationTests(unittest.TestCase):
    def test_matched_order_independent_scores_and_shared_warmup(self):
        base=[row(),row('2',.4,False)];candidate=copy.deepcopy(base);candidate[0].update(home_probability=.7,away_probability=.3)
        all_games=compare_samples({'base':base,'candidate':list(reversed(candidate))})
        warm=compare_samples({'base':base,'candidate':candidate},established=True)
        self.assertEqual(all_games['games'],2);self.assertEqual(warm['games'],1)
        self.assertEqual(warm['game_ids'],['1'])
        self.assertLess(all_games['difference_from_baseline']['candidate']['log_loss'],0)
        self.assertEqual(all_games['sample_sha256'],compare_samples({'base':list(reversed(base)),'candidate':candidate})['sample_sha256'])

    def test_different_samples_cutoffs_outcomes_eligibility_and_sources_fail(self):
        base=[row()]
        for change in [dict(game_id='2'),dict(home_win=0),dict(eligible_for_evaluation=False),
                       dict(forecast_cutoff='2026-10-20T13:00:00Z'),dict(home='C'),
                       dict(source_data_sha256='different'),dict(kind='issued_live')]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):compare_samples({'base':base,'candidate':[{**row(),**change}]})
        for bad in [[],[row(),row()],[{**row(),'home_probability':None}],[{**row(),'away_probability':.9}]]:
            with self.assertRaises(ValueError):compare_samples({'base':base,'candidate':bad})

    def test_missing_variant_fails_instead_of_dropping_a_game(self):
        original=row();original['probability_models']={key:{'home_probability':.6,'away_probability':.4} for key in ['base','injury','boosted']}
        self.assertEqual(compare_variants([original])['games'],1)
        del original['probability_models']['injury']
        with self.assertRaises(ValueError):compare_variants([original])

    def test_favorite_calibration_uses_both_sides_and_boundary_bins(self):
        rows=[row('1',.6),row('2',.4),row('3',.65),row('4',.5),row('5',1.)]
        rows[1]['home_win']=0
        bands={r['band']:r for r in favorite_bands(rows)}
        self.assertEqual(bands['60–65%']['games'],2);self.assertEqual(bands['60–65%']['wins'],2)
        self.assertEqual(bands['65–70%']['games'],1)
        self.assertEqual(bands['50–55%']['wins'],1)
        self.assertEqual(bands['95–100%']['games'],1)
        self.assertLess(bands['60–65%']['lower_95'],1)
        self.assertAlmostEqual(bands['60–65%']['upper_95'],1)

    def test_duplicate_training_rows_are_rejected_before_fitting(self):
        try:from nba_forecast.training import fit_heads
        except ImportError:self.skipTest('Scientific training dependencies unavailable')
        with self.assertRaisesRegex(ValueError,'Duplicate game IDs'):fit_heads([{'game_id':'x'},{'game_id':'x'}],2027)
