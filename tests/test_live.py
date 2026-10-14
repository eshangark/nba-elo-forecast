"""Live issuance, corrections, timing, and failed-publication guarantees."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nba_forecast.live import build_snapshot, event_kind
from nba_forecast.model import Parameters
from test_model import game

ROSTER = {'A': 'Team A', 'B': 'Team B'}
SEASON = '2026-27'
PARAMS = Parameters()


def completed(identifier='1', day='2026-10-20'):
    g = game(identifier, day)
    g['season'] = 2027
    g['last_play_at'] = day+'T23:59:00Z'
    return g


def scheduled(identifier='1', day='2026-10-20'):
    g = completed(identifier, day)
    g['event_state'] = 'pre'
    for side in ['home', 'away']:
        g[side] = {k: g[side][k] for k in ['id', 'name']}
    g.pop('last_play_at')
    return g


def snapshot(previous=None, games=None, pending=None, now='2026-10-19T20:00:00Z'):
    return build_snapshot(previous, games or [], pending or [], PARAMS, ROSTER, now, SEASON)


class LiveTests(unittest.TestCase):
    def test_identical_poll_does_not_add_a_forecast_revision(self):
        first = snapshot(pending=[scheduled()])
        second = snapshot(first, pending=[scheduled()], now='2026-10-19T21:00:00Z')
        self.assertEqual(first['_internal']['forecasts'], second['_internal']['forecasts'])
        self.assertEqual(first['upcoming'], second['upcoming'])
        self.assertEqual(first['result']['rankings'], second['result']['rankings'])

    def test_final_result_updates_once_and_retains_issued_forecast(self):
        first = snapshot(pending=[scheduled()])
        second = snapshot(first, games=[completed()], now='2026-10-21T02:00:00Z')
        third = snapshot(second, games=[completed()], now='2026-10-21T03:00:00Z')
        self.assertEqual(second['result']['rankings'], third['result']['rankings'])
        self.assertEqual(second['_internal']['forecasts'], first['_internal']['forecasts'])
        row = second['result']['predictions'][0]
        self.assertEqual(row['home_probability'], first['upcoming'][0]['home_probability'])
        self.assertEqual(row['kind'], 'issued_live')
        self.assertEqual(second['result']['metrics_all_issued']['games'], 1)
        self.assertEqual(second['result']['metrics']['games'], 0)  # warmup
        self.assertTrue(all(t['games'] == 1 for t in second['result']['rankings']))

    def test_backfill_does_not_fabricate_a_live_prediction(self):
        result = snapshot(games=[completed()], now='2026-10-21T02:00:00Z')
        self.assertEqual(result['_internal']['forecasts'], [])
        self.assertIsNone(result['result']['predictions'][0]['home_probability'])
        self.assertEqual(result['result']['metrics_all_issued']['games'], 0)

    def test_corrected_box_rebuilds_ratings_without_rewriting_forecasts(self):
        first = snapshot(pending=[scheduled()])
        second = snapshot(first, games=[completed()], now='2026-10-21T02:00:00Z')
        correction = completed()
        correction['away'].update(fgm=55, points=130, largest_lead=40)
        changed = snapshot(second, games=[correction], now='2026-10-21T03:00:00Z')
        self.assertNotEqual(changed['result']['rankings'], second['result']['rankings'])
        self.assertEqual(changed['_internal']['forecasts'], first['_internal']['forecasts'])
        self.assertEqual(len(changed['_internal']['corrections']), 1)
        self.assertEqual(changed['result']['predictions'][0]['home_win'], 0)

    def test_future_schedule_projects_rest_without_inventing_ratings(self):
        first = snapshot(pending=[scheduled(), scheduled('2', '2026-10-21')])
        self.assertEqual(first['upcoming'][1]['home_context']['rest'], 0)
        self.assertTrue(first['upcoming'][1]['scheduled_context_projected'])
        self.assertEqual(first['upcoming'][1]['home_rating'], 1500)
        second = snapshot(first, games=[completed()], pending=[scheduled('2', '2026-10-21')], now='2026-10-21T02:00:00Z')
        self.assertEqual(second['_internal']['forecasts'][:2], first['_internal']['forecasts'])
        self.assertEqual(len(second['_internal']['forecasts']), 3)
        self.assertNotEqual(second['upcoming'][0]['home_rating'], 1500)

    def test_game_already_started_cannot_receive_a_new_forecast(self):
        result = snapshot(pending=[scheduled()], now='2026-10-20T23:30:00Z')
        self.assertEqual(result['upcoming'], [])
        self.assertEqual(result['_internal']['forecasts'], [])
        self.assertEqual(len(result['awaiting_final']), 1)

    def test_invalid_game_cannot_mutate_a_previous_valid_snapshot(self):
        first = snapshot(pending=[scheduled()])
        original = copy.deepcopy(first)
        bad = completed(); bad['away']['tov'] = -1
        with self.assertRaises(ValueError):
            snapshot(first, games=[bad], now='2026-10-21T02:00:00Z')
        self.assertEqual(first, original)

    def test_future_source_time_or_completion_is_rejected(self):
        with self.assertRaises(ValueError):
            build_snapshot(None, [], [], PARAMS, ROSTER, '2026-10-19T20:00:00Z', SEASON,
                           source_manifest=[{'retrieved_at': '2026-10-19T21:00:00Z'}])
        with self.assertRaises(ValueError):
            snapshot(games=[completed()], now='2026-10-20T23:30:00Z')

    def test_known_completed_game_cannot_silently_disappear(self):
        first = snapshot(games=[completed()], now='2026-10-21T02:00:00Z')
        with self.assertRaises(ValueError):
            snapshot(first, now='2026-10-21T03:00:00Z')

    def test_preseason_cup_final_and_unknown_category_are_not_regular_games(self):
        event = {'id': '1', 'season': {'year': 2027, 'type': 1},
                 'competitions': [{'type': {'abbreviation': 'STD'}, 'status': {'type': {'state': 'pre', 'completed': False}}}]}
        self.assertEqual(event_kind(event, 2027), 'excluded')
        event['season']['type'] = 2
        event['competitions'][0]['type']['abbreviation'] = 'CC'
        self.assertEqual(event_kind(event, 2027), 'excluded')
        event['competitions'][0]['type']['abbreviation'] = 'UNKNOWN'
        with self.assertRaises(ValueError): event_kind(event, 2027)

    def test_collector_failure_preserves_published_file(self):
        from scripts import update_live
        from datetime import datetime
        from nba_forecast.model import EASTERN
        from nba_forecast.seasons import current_season
        root = Path(__file__).resolve().parents[1]
        season = current_season(datetime.now(EASTERN).date())
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)/season; folder.mkdir()
            old = snapshot(pending=[scheduled()]); old['season'] = season
            published = folder/'live.json'; published.write_text(json.dumps(old))
            before = published.read_bytes()
            index = Path(td)/'index.json'; index.write_text(json.dumps({'seasons': []}))
            with patch('sys.argv', ['update_live.py', '--cities', 'unused', '--archives', td,
                                    '--parameters', str(root/'models/nba-v0.2/parameters.json')]), \
                 patch.object(update_live, 'Cities', return_value=object()), \
                 patch.object(update_live, 'Client', return_value=object()), \
                 patch.object(update_live, 'collect', side_effect=RuntimeError('feed unavailable')):
                with self.assertRaises(RuntimeError): update_live.main()
            self.assertEqual(published.read_bytes(), before)
            self.assertEqual(json.loads((folder/'update_status.json').read_text())['state'], 'failed')

    def test_single_writer_lock_rejects_overlap_and_releases_after_failure(self):
        from nba_forecast.live import live_lock
        with tempfile.TemporaryDirectory() as td:
            with live_lock(td):
                with self.assertRaises(RuntimeError):
                    with live_lock(td): pass
            with self.assertRaises(ValueError):
                with live_lock(td): raise ValueError('simulate crash')
            with live_lock(td): pass
