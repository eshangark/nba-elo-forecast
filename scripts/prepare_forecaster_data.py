"""Download/cache free historical player boxes and official morning injury reports."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_forecast.data import write_json
from nba_forecast.injuries import parse_pdf
from nba_forecast.model import slate_date
from nba_forecast.training import load_history


def download(url):
    with urlopen(url, timeout=30) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/raw/forecasters'))
    parser.add_argument('--offline', action='store_true', help='Only validate existing cached files')
    args = parser.parse_args()
    seasons = load_history(Path(__file__).resolve().parents[1])
    players, injuries = args.output/'players', args.output/'injuries'
    players.mkdir(parents=True, exist_ok=True)
    injuries.mkdir(parents=True, exist_ok=True)
    sources = []
    for year in seasons:
        path = players/f'player_box_{year}.parquet'
        url = f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_boxscores/{path.name}'
        if not path.exists():
            if args.offline:
                raise ValueError('Missing cached player archive: '+str(path))
            path.write_bytes(download(url))
        sources.append({'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    days = sorted({str(slate_date(g)) for games in seasons.values() for g in games})
    def collect(day):
        path = injuries/f'{day}.pdf'
        failures = []
        if not path.exists() and not args.offline:
            suffixes = ['08_30AM', '08AM'] if day >= '2025-12-01' else ['08AM', '08_30AM']
            for suffix in suffixes:
                url = f'https://ak-static.cms.nba.com/referee/injury/Injury-Report_{day}_{suffix}.pdf'
                try:
                    raw = download(url)
                    if not raw.startswith(b'%PDF'):
                        raise ValueError('Expected a PDF')
                    path.write_bytes(raw)
                    break
                except Exception as exc:
                    failures.append({'url': url, 'error': str(exc)})
        if not path.exists():
            return day, None, {'date': day, 'state': 'unavailable', 'attempts': failures}
        try:
            report = parse_pdf(path.read_bytes())
            # Each format is a different public filename, not a retry of a denied URL.
            report['source_date'] = day
            return day, report, {'date': day, 'state': 'parsed', 'sha256': report['sha256'], 'attempts': failures}
        except Exception as exc:
            return day, None, {'date': day, 'state': 'invalid', 'error': str(exc)}
    reports, audit = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, (day, report, record) in enumerate(pool.map(collect, days), 1):
            if report:
                reports[day] = report
            audit.append(record)
            if i % 100 == 0:
                print('Checked', i, 'of', len(days), flush=True)
    write_json(args.output/'reports.json', reports)
    write_json(args.output/'sources.json', {'players': sources, 'injuries': audit})
    if len(reports) < .95*len(days):
        raise ValueError('Insufficient verified morning-report coverage; inspect sources.json before fitting')
    print('Validated', len(reports), 'of', len(days), 'official morning reports', flush=True)


if __name__ == '__main__':
    main()
