"""Validated postgame player inputs; missing records are never zero minutes."""

import math
from .data import integer
from .injuries import player_key


def game_score(row):
    return (row['points']+.4*row['fgm']-.7*row['fga']-.4*(row['fta']-row['ftm'])
            +.7*row['oreb']+.3*row['dreb']+row['stl']+.7*row['ast']+.7*row['blk']-.4*row['pf']-row['tov'])


def validated_players(rows, team):
    if len(rows) < 5 or len({r['athlete'] for r in rows}) != len(rows):
        raise ValueError('Incomplete or duplicate player identities')
    for field in ['points', 'fgm', 'fga', 'threem', 'threea', 'ftm', 'fta', 'oreb', 'dreb', 'ast', 'stl', 'tov']:
        if sum(r[field] for r in rows) != team[field]:
            raise ValueError(f'Player total disagrees with team {field}')
    for r in rows:
        if not all(math.isfinite(r[k]) for k in ['minutes', 'blk', 'pf']) or not 0 < r['minutes'] <= 65:
            raise ValueError('Invalid player minutes/counts')
        for field in ['points', 'fgm', 'fga', 'threem', 'threea', 'ftm', 'fta', 'oreb', 'dreb', 'ast', 'stl', 'tov', 'blk', 'pf']:
            value = r[field]
            if not math.isfinite(value) or value < 0 or value != int(value):
                raise ValueError('Invalid individual player count: '+field)
        if (r['fgm'] > r['fga'] or r['threem'] > r['threea'] or r['threem'] > r['fgm']
                or r['threea'] > r['fga'] or r['ftm'] > r['fta']
                or r['points'] != 2*r['fgm']+r['threem']+r['ftm']):
            raise ValueError('Contradictory individual player shooting/points')
    minutes = sum(r['minutes'] for r in rows)
    if min(abs(minutes-(240+25*ot)) for ot in range(7)) > 8:
        raise ValueError('Incomplete player minute total')
    return [{'athlete': r['athlete'], 'minutes': r['minutes'], 'game_score': game_score(r)} for r in rows]


def parse_player_summary(payload, game):
    if str(payload['header']['id']) != game['game_id']:
        raise ValueError('Player summary/game identity mismatch')
    tables = {str(t['team']['id']): t for t in payload['boxscore']['players']}
    result, aliases, failures = {}, {}, []
    for side in ['home', 'away']:
        team = game[side]['id']
        try:
            table = tables[team]['statistics'][0]
            rows = []
            for athlete in table['athletes']:
                stats = athlete.get('stats', [])
                if not stats:
                    if not athlete.get('didNotPlay', False):
                        raise ValueError('Missing active-player statistics')
                    continue
                if len(stats) != len(table['labels']):
                    raise ValueError('Incomplete player statistics')
                values = dict(zip(table['labels'], stats))
                minutes = values['MIN']
                minutes = sum(float(v)/(60**i) for i, v in enumerate(str(minutes).split(':')))
                if minutes == 0:
                    continue
                row = {'athlete': str(int(athlete['athlete']['id'])), 'minutes': minutes}
                for label, field in [('PTS', 'points'), ('OREB', 'oreb'), ('DREB', 'dreb'), ('AST', 'ast'),
                                     ('STL', 'stl'), ('BLK', 'blk'), ('TO', 'tov'), ('PF', 'pf')]:
                    row[field] = integer(values[label], label)
                for label, prefix in [('FG', 'fg'), ('3PT', 'three'), ('FT', 'ft')]:
                    made, attempted = values[label].split('-')
                    row[prefix+'m'], row[prefix+'a'] = integer(made, label), integer(attempted, label)
                rows.append(row)
                aliases.setdefault(player_key(athlete['athlete']['displayName']), set()).add(row['athlete'])
            result[team] = validated_players(rows, game[side])
        except (KeyError, ValueError, StopIteration) as exc:
            result[team] = None
            failures.append({'team_id': team, 'error': str(exc)})
    return result, {name: sorted(ids) for name, ids in aliases.items()}, failures
