"""Release-data checks: complete seasons and exported probability/feature parity."""

import csv
import json
import math
import unittest
from collections import Counter
from pathlib import Path

from nba_forecast.model import Parameters, box_features, performance
from nba_forecast.replay import replay

ROOT = Path(__file__).resolve().parents[1]


class HistoryTests(unittest.TestCase):
    def test_release_inputs_and_exports_match_the_frozen_engine(self):
        params = Parameters(**json.loads((ROOT / 'models/nba-v0.2/parameters.json').read_text()))
        for end_year in range(2022, 2027):
            label = f'{end_year-1}-{str(end_year)[-2:]}'
            folder = ROOT / 'data/seasons' / label
            games = json.loads((folder / 'games.json').read_text())
            snapshot = json.loads((folder / 'snapshot.json').read_text())['result']
            self.assertEqual(len(games), 1230)
            self.assertEqual(len({g['game_id'] for g in games}), 1230)
            counts = Counter(g[s]['id'] for g in games for s in ['home', 'away'])
            self.assertEqual(len(counts), 30)
            self.assertEqual(set(counts.values()), {82})
            rerun = replay(games, params, fitted=True, warmup_games=10)
            self.assertEqual(rerun['metrics'], snapshot['metrics'])
            self.assertEqual(rerun['predictions'], snapshot['predictions'])
            with (folder / 'model_features.csv').open() as f:
                rows = list(csv.DictReader(f))
            with (folder / 'team_games.csv').open() as f:
                raw_rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2460)
            self.assertEqual(len(raw_rows), 2460)
            by_id = {g['game_id']: g for g in games}
            for row in rows:
                for name, value in row.items():
                    if name.startswith(('pregame_', 'postgame_')):
                        self.assertTrue(math.isfinite(float(value)), (label, name))
                g = by_id[row['game_id']]
                side = row['side']; other = 'away' if side == 'home' else 'home'
                features = box_features(g[side], g[other])
                for k, value in enumerate(features, 1):
                    self.assertAlmostEqual(float(row[f'postgame_x{k}']), value, places=12)
                self.assertAlmostEqual(float(row['postgame_agpf']), performance(g[side], g[other], params.alpha_weights), places=12)
                logit = math.log(10) * ((float(row['pregame_elo']) - float(row['pregame_opponent_elo']) + float(row['pregame_home_offset'])) / params.c - params.fatigue_weight * math.log(float(row['pregame_ortf']) / float(row['pregame_trof'])))
                self.assertAlmostEqual(float(row['win_probability']), 1 / (1 + math.exp(-logit)), places=12)
