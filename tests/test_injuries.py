"""Publication cutoffs, official PDF continuity and source outages."""
from datetime import datetime
import importlib.util
from pathlib import Path
import unittest
from urllib.error import HTTPError

from nba_forecast.injuries import latest_report, join_report, parse_pdf, player_key
from nba_forecast.model import timestamp


class InjuryTests(unittest.TestCase):
    def test_exact_names_ignore_suffix_and_numeric_id_representation(self):
        self.assertEqual(player_key('Brown Jr., Troy'), player_key('Troy Brown Jr.'))
        self.assertEqual(player_key('Dončić, Luka'), player_key('Luka Doncic'))

    def test_future_report_cannot_join_to_a_forecast(self):
        with self.assertRaises(ValueError):
            join_report({'published_at': '2026-10-20T15:00:00Z'}, [], {}, timestamp('2026-10-20T14:00:00Z'))

    @unittest.skipUnless(importlib.util.find_spec('pdfplumber'), 'PDF dependency not installed')
    def test_real_old_and_continuation_formats_preserve_player_rows(self):
        expected = [('2021-11-10', 105), ('2023-12-18', 118)]
        for day, count in expected:
            raw = (Path(__file__).parent/'fixtures'/f'injury-{day}.pdf').read_bytes()
            parsed = parse_pdf(raw)
            self.assertEqual(sum(r['player'] is not None for r in parsed['records']), count)
            self.assertFalse(any(r['team'].startswith('Page') for r in parsed['records']))
            self.assertEqual(str(timestamp(parsed['published_at']).date()), day)
            self.assertTrue(any(r['status'] == 'NOT YET SUBMITTED' for r in parsed['records']))

    @unittest.skipUnless(importlib.util.find_spec('pdfplumber'), 'PDF dependency not installed')
    def test_official_index_future_links_and_stale_report_are_not_usable(self):
        raw = (Path(__file__).parent/'fixtures/injury-2023-12-18.pdf').read_bytes()
        old = 'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2023-12-18_08AM.pdf'
        future = 'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2023-12-18_11AM.pdf'
        calls = []
        def fetch(url):
            calls.append(url)
            return f'<a href="{future}">future</a><a href="{old}">morning</a>'.encode() if 'official.nba.com' in url else raw
        report, source = latest_report('2023-24', timestamp('2023-12-18T14:00:00Z'), fetch=fetch)
        self.assertEqual(source['url'], old)
        self.assertNotIn(future, calls)
        with self.assertRaises(ValueError):
            latest_report('2023-24', timestamp('2023-12-20T14:00:00Z'), fetch=fetch)
        with self.assertRaises(RuntimeError):
            latest_report('2023-24', timestamp('2023-12-18T14:00:00Z'), fetch=lambda url: (_ for _ in ()).throw(RuntimeError('feed outage')))

    @unittest.skipUnless(importlib.util.find_spec('pdfplumber'), 'PDF dependency not installed')
    def test_public_dated_feed_survives_index_outage_without_retrying_denied_url(self):
        raw = (Path(__file__).parent/'fixtures/injury-2023-12-18.pdf').read_bytes()
        calls = []
        def fetch(url):
            calls.append(url)
            if url.endswith('2023-12-18_08_30AM.pdf'):
                return raw
            raise HTTPError(url, 403 if 'official.nba.com' in url else 404, 'unavailable', None, None)
        _, source = latest_report('2023-24', timestamp('2023-12-18T14:00:00Z'), fetch=fetch)
        self.assertTrue(source['url'].endswith('08_30AM.pdf'))
        self.assertEqual(len(calls), len(set(calls)))
        self.assertEqual(sum('official.nba.com' in url for url in calls), 1)


if __name__ == '__main__':
    unittest.main()
