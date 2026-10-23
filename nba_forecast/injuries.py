"""Official timestamped NBA injury reports with explicit unknown coverage."""

from datetime import datetime, timedelta
from io import BytesIO
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .model import EASTERN, slate_date, timestamp


def normalized(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]', '', text)


def player_key(name):
    if ',' in name:
        last, first = name.split(',', 1)
        name = first+' '+last
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return ''.join(w for w in re.findall('[a-z0-9]+', text) if w not in ['jr', 'sr', 'ii', 'iii', 'iv', 'v'])


def parse_pdf(raw):
    """Use physical table coordinates; never treat PDF stream order as row order."""
    import pdfplumber
    records, current_date, matchup, team, bounds = [], None, None, None, None
    with pdfplumber.open(BytesIO(raw)) as pdf:
        text = pdf.pages[0].extract_text() or ''
        match = re.search(r'Injury\s*Report:\s*(\d{2}/\d{2}/\d{2,4})\s+(\d{2}:\d{2})\s*(AM|PM)', text, re.I)
        if not match:
            raise ValueError('Injury report has no publication timestamp')
        fmt = '%m/%d/%y %I:%M %p' if len(match[1]) == 8 else '%m/%d/%Y %I:%M %p'
        published = datetime.strptime(' '.join(match.groups()), fmt).replace(tzinfo=EASTERN)
        for number, page in enumerate(pdf.pages, 1):
            words = page.extract_words(x_tolerance=1, y_tolerance=2)
            anchor = next((w for w in words if normalized(w['text']) == 'matchup' and w['top'] < page.height*.35), None)
            headers = {}
            if anchor:
                line = [w for w in words if abs(w['top']-anchor['top']) < 2]
                for w in line:
                    token = normalized(w['text'])
                    field = {'team': 'team', 'player': 'player', 'playername': 'player', 'current': 'status',
                             'currentstatus': 'status', 'reason': 'reason', 'matchup': 'matchup', 'gametime': 'time'}.get(token)
                    if field:
                        headers[field] = w
                if 'time' not in headers:
                    game_words = [w for w in line if normalized(w['text']) == 'game' and w['x0'] < anchor['x0']]
                    if len(game_words) >= 2:
                        headers['time'] = game_words[-1]
                if set(headers) != {'team', 'player', 'status', 'reason', 'matchup', 'time'}:
                    raise ValueError(f'Incomplete injury table header on page {number}')
                bounds = [0]+[headers[k]['x0']-2 for k in ['time', 'matchup', 'team', 'player', 'status', 'reason']]+[page.width]
                ymin = max(w['bottom'] for w in headers.values())+2
            else:
                if bounds is None:
                    raise ValueError('Injury table starts without column definitions')
                captions = [w for w in words if normalized(w['text']) in ['injury', 'report'] and w['top'] < 80 and w['x0'] < 450]
                ymin = max((w['bottom'] for w in captions), default=70)+3
            groups = []
            for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
                if word['top'] < ymin:
                    continue
                if groups and abs(groups[-1][0]-word['top']) < 2:
                    groups[-1][1].append(word)
                else:
                    groups.append((word['top'], [word]))
            for _, row in groups:
                if re.fullmatch(r'page\d+of\d+', normalized(' '.join(w['text'] for w in row))):
                    continue
                columns = [' '.join(w['text'] for w in sorted(row, key=lambda w: w['x0']) if left <= w['x0'] < right)
                           for left, right in zip(bounds, bounds[1:])]
                date_text, _, match_text, team_text, player, status, reason = columns
                found = re.search(r'\d{2}/\d{2}/\d{4}', date_text)
                if found:
                    current_date = datetime.strptime(found[0], '%m/%d/%Y').date().isoformat()
                if '@' in match_text:
                    matchup = match_text.replace(' ', '')
                if team_text:
                    team = team_text
                if not (current_date and matchup and team):
                    if player or status:
                        raise ValueError('Injury row has unresolved game/team identity')
                    continue
                identity = {'game_date': current_date, 'matchup': matchup, 'team': team}
                if 'notyetsubmitted' in normalized(reason+status+player):
                    records.append({**identity, 'player': None, 'status': 'NOT YET SUBMITTED'})
                    continue
                if team_text:
                    records.append({**identity, 'player': None, 'status': 'TEAM ROW'})
                if status:
                    if status not in ['Out', 'Doubtful', 'Questionable', 'Probable', 'Available'] or not player:
                        raise ValueError('Unrecognized injury designation/player')
                    records.append({**identity, 'player': player, 'status': status})
    return {'published_at': published.isoformat(), 'sha256': hashlib.sha256(raw).hexdigest(), 'records': records}


TEAM_CODES = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN', 'Charlotte Hornets': 'CHA',
    'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE', 'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN',
    'Detroit Pistons': 'DET', 'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'LA Clippers': 'LAC', 'Los Angeles Clippers': 'LAC', 'Los Angeles Lakers': 'LAL', 'Memphis Grizzlies': 'MEM',
    'Miami Heat': 'MIA', 'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN', 'New Orleans Pelicans': 'NOP',
    'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC', 'Orlando Magic': 'ORL', 'Philadelphia 76ers': 'PHI',
    'Phoenix Suns': 'PHX', 'Portland Trail Blazers': 'POR', 'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS',
    'Toronto Raptors': 'TOR', 'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS'}


def join_report(report, games, aliases, cutoff):
    if timestamp(report['published_at']) > cutoff:
        raise ValueError('Injury report was published after the prediction cutoff')
    names = {normalized(g[s]['name']): g[s]['id'] for g in games for s in ['home', 'away']}
    for short, full in [('LA Clippers', 'Los Angeles Clippers'), ('LA Lakers', 'Los Angeles Lakers')]:
        identifier = names.get(normalized(short)) or names.get(normalized(full))
        if identifier:
            names[normalized(short)] = names[normalized(full)] = identifier
    targets = {(str(slate_date(g)), g[s]['id']): g for g in games for s in ['home', 'away']}
    result = {}
    for row in report['records']:
        team = names.get(normalized(row['team']))
        game = targets.get((row['game_date'], team))
        if not game:
            continue  # Includes postponed games and other dates in the report.
        expected = TEAM_CODES.get(game['away']['name'], '')+'@'+TEAM_CODES.get(game['home']['name'], '')
        if row['matchup'] != expected:
            raise ValueError('Injury report/canonical matchup mismatch')
        value = result.setdefault(game['game_id'], {}).setdefault(team, {'submitted': True, 'players': []})
        if row['status'] == 'NOT YET SUBMITTED':
            value['submitted'] = False
        elif row['player']:
            identities = aliases.get(player_key(row['player']), [])
            athlete = identities[0] if len(identities) == 1 else None
            value['players'].append({'athlete': athlete, 'name': row['player'], 'status': row['status']})
    return result


def latest_report(season, now, max_age_hours=16, fetch=None):
    """Read the official index once and a listed PDF once; failures are visible."""
    fetch = fetch or (lambda url: urlopen(url, timeout=20).read())
    url = f'https://official.nba.com/nba-injury-report-{season}-season/'
    try:
        html = fetch(url).decode('utf-8')
    except (URLError, TimeoutError):
        html = ''  # The public dated PDF feed is independent of the index page.
    links = set(re.findall(r'https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_[^\s"<>]+\.pdf', html))
    candidates = []
    for link in links:
        match = re.search(r'Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})(?:_(\d{2}))?(AM|PM)\.pdf$', link)
        if not match:
            continue
        day, hour, minute, meridian = match.groups()
        # Legacy hour-only URLs point to the half-hour report. Verify the PDF header.
        issued = datetime.strptime(f'{day} {hour}:{minute or "30"}{meridian}', '%Y-%m-%d %I:%M%p').replace(tzinfo=EASTERN)
        if issued <= now:
            candidates.append((issued, link))
    sources = [max(candidates)[1]] if candidates else []
    local = now.astimezone(EASTERN)
    rounded = local.replace(minute=local.minute//15*15, second=0, microsecond=0)
    # At most four distinct, already-due public report versions. No denied URL is retried.
    sources.extend('https://ak-static.cms.nba.com/referee/injury/Injury-Report_'
                   +(rounded-timedelta(minutes=15*i)).strftime('%Y-%m-%d_%I_%M%p')+'.pdf' for i in range(4))
    failures = []
    for source in dict.fromkeys(sources):
        try:
            parsed = parse_pdf(fetch(source))
            published = timestamp(parsed['published_at'])
            if published > now or now-published > timedelta(hours=max_age_hours):
                raise ValueError('Official injury report is future-dated or stale')
            return parsed, {'url': source, 'published_at': parsed['published_at'], 'sha256': parsed['sha256']}
        except (URLError, TimeoutError, ValueError) as exc:
            failures.append(str(exc))
    raise ValueError('No current verified official injury PDF: '+'; '.join(failures))
